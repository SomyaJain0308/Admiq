from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.app.database import get_db
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff, StaffCollege
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.models.Message import Message
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
from backend.app.models.Chunk import Chunk
from backend.app.services.auth_services import verify_college_access
from backend.app.services.csv_export import rows_to_csv_response
from backend.app.services.tenant_service import save_staff_message
from backend.app.services.whatsapp_service import send_staff_initiated_message
from backend.app.schemas.students import StudentMessageCreate, StudentMessageResponse, StudentNotesUpdate, StudentAssignUpdate
from backend.app.config import get_settings
from backend.app.monitoring.logging_utils import get_logger
from backend.app.monitoring.low_confidence import LOW_CONFIDENCE_QUERIES_RESOLVED
from backend.app.rag.staff_reply_context import reconstruct_staff_answer

logger = get_logger()

# Bounds how much conversation gets fed to the reconstruction LLM call for a
# save-as-answer request. Unlike the queue's reply endpoint (which anchors
# to one flagged question and grabs the 4 messages around it), there's no
# single question here - the whole thread is fair game per how this was
# scoped - so this just keeps a very long-running student thread from
# turning into an unbounded prompt.
SAVE_AS_ANSWER_CONTEXT_LIMIT = 40

router = APIRouter(tags=["Students"], prefix="/router/students")


@router.get("/{college_id}")
async def get_students(
    college_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    search: str | None = Query(default=None, max_length=200),
    assigned_to: str | None = Query(default=None, description="A staff_id to filter to that staff member's students, or 'unassigned' for students with no assigned staff member"),
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Paginated + searched server-side now rather than the frontend fetching
    # every student for the college and filtering client-side - that stopgap
    # was fine at low volume but doesn't scale as a college's student list
    # grows into the hundreds/thousands.
    query = select(Student).where(Student.college_id == college_id)
    count_query = select(func.count()).select_from(Student).where(Student.college_id == college_id)

    if search:
        term = f"%{search.strip()}%"
        search_filter = or_(Student.student_name.ilike(term), Student.student_phone.ilike(term), Student.course_interest.ilike(term))
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if assigned_to is not None:
        # "Assigned to" only means something once staff can actually filter
        # by it - otherwise it's a label nobody can query, which is the
        # exact gap this closes.
        if assigned_to.strip().lower() == "unassigned":
            assigned_filter = Student.assigned_to.is_(None)
        else:
            try:
                assigned_staff_id = int(assigned_to)
            except ValueError:
                raise HTTPException(status_code=400, detail="assigned_to must be a staff id or 'unassigned'")
            assigned_filter = Student.assigned_to == assigned_staff_id
        query = query.where(assigned_filter)
        count_query = count_query.where(assigned_filter)

    total = (await db.execute(count_query)).scalar_one()

    # Hottest leads first by default - the whole point of lead scoring is
    # surfacing who staff should look at first, so that should be true here
    # too, not just on the dashboard chart.
    query = query.order_by(Student.lead_score.desc()).offset((page - 1) * page_size).limit(page_size)
    students = (await db.execute(query)).scalars().all()

    return {"items": students, "total": total, "page": page, "page_size": page_size}


@router.get("/{college_id}/export")
async def export_students(
    college_id: int,
    search: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Same search filter as the list endpoint, but no pagination - export is
    # meant to hand someone the full matching set for a spreadsheet, not one
    # page of it.
    query = select(Student).where(Student.college_id == college_id)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(Student.student_name.ilike(term), Student.student_phone.ilike(term), Student.course_interest.ilike(term)))
    query = query.order_by(Student.lead_score.desc())
    students = (await db.execute(query)).scalars().all()

    rows = [
        {
            "student_name": s.student_name or "",
            "student_phone": s.student_phone,
            "course_interest": s.course_interest or "",
            "lead_score": s.lead_score,
            "summary": (s.summary or "").replace("\n", " "),
            "created_at": s.created_at.isoformat() if s.created_at else "",
        }
        for s in students
    ]
    columns = ["student_name", "student_phone", "course_interest", "lead_score", "summary", "created_at"]
    return rows_to_csv_response(rows, columns, filename=f"students_college_{college_id}.csv")


@router.get("/{college_id}/lead-scores")
async def get_student_lead_scores(
    college_id: int,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Backs the Overview page's lead-score distribution chart, which needs
    # every student's score (not full records) to bucket into a histogram -
    # a single narrow column, not a paginated page of the list endpoint
    # above, which would silently truncate the chart for any college over
    # one page of students.
    #
    # Must stay ABOVE /{college_id}/{student_id} below: that route has no
    # `:int` type constraint in the path itself (only on the function
    # parameter), so Starlette's router matches "lead-scores" as a literal
    # student_id string before FastAPI's own int validation ever runs -
    # and a failed validation there is a 422, not a "try the next route"
    # fallthrough. Same reasoning as /{college_id}/export just above.
    result = await db.execute(select(Student.lead_score).where(Student.college_id == college_id))
    lead_scores = [row[0] for row in result.all()]
    return {"lead_scores": lead_scores}


@router.get("/{college_id}/{student_id}")
async def get_student(college_id: int, student_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/view_convo/{college_id}/{student_id}")
async def view_conversation(college_id: int, student_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    convo_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.student_id == student_id).order_by(Message.created_at.asc()))
    convo = convo_result.scalars().all()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@router.post("/{college_id}/{student_id}/message", response_model=StudentMessageResponse)
async def message_student(
    college_id: int,
    student_id: int,
    payload: StudentMessageCreate,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Direct outbound message from a staff member, independent of the
    # low-confidence queue. Reuses the same WhatsApp send + message-save
    # path as the queue's reply endpoint, but without a query_id to resolve,
    # no expiry, and no retrieval-chunk embedding - this is just "say this
    # to the student now," not "teach the assistant this answer."
    staff_id = membership.staff_id
    settings = get_settings()

    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    whatsapp_number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.college_id == college_id).limit(1))
    whatsapp_number = whatsapp_number_result.scalars().first()
    if not whatsapp_number:
        raise HTTPException(status_code=503, detail="No WhatsApp number configured for this college")

    # WhatsApp only allows free-form text within 24h of the STUDENT's last
    # message to us - a staff-initiated message like this one is exactly
    # the case where that window may have already closed, so this looks up
    # the student's own last inbound activity (not our own last reply,
    # which doesn't extend the window) and falls back to a template send if
    # it's been too long.
    last_session_result = await db.execute(
        select(StudentSession.last_message_at)
        .where(StudentSession.college_id == college_id, StudentSession.student_id == student_id)
        .order_by(StudentSession.last_message_at.desc())
        .limit(1)
    )
    last_inbound_message_at = last_session_result.scalars().first()

    send_result = await send_staff_initiated_message(
        phone_number_id=whatsapp_number.phone_number_id,
        to=student.whatsapp_user_id,
        message=payload.content,
        access_token=settings.whatsapp_access_token,
        last_inbound_message_at=last_inbound_message_at,
        template_name=settings.whatsapp_staff_template_name,
        template_language_code=settings.whatsapp_staff_template_language_code,
    )
    if not send_result["ok"]:
        logger.error(f"Failed to deliver staff message to student_id={student_id} (channel={send_result.get('channel')})")

    # Save it either way, matching the low-confidence reply endpoint's
    # behavior - the message was genuinely sent by staff even if WhatsApp's
    # API call failed, and the frontend surfaces delivery status separately
    # via `delivered` rather than silently dropping the record.
    staff_message = await save_staff_message(db, college_id=college_id, student_id=student_id, staff_id=staff_id, content=payload.content)

    saved_as_answer = False
    reconstructed_question = None
    save_error = None

    if payload.save_as_answer:
        try:
            # LowConfidenceQuery.question_message_id is NOT NULL with a real
            # FK to messages, and it's not just descriptive - the queue's
            # reply flow uses it to anchor "the 4 messages around this
            # question". There's no flagged question here, so instead we
            # anchor to the most recent message the student themselves sent
            # in this conversation, whatever its position (staff messages
            # sent after it don't disqualify it).
            anchor_result = await db.execute(
                select(Message)
                .where(Message.college_id == college_id, Message.student_id == student_id, Message.messager_role == "student")
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            anchor_message = anchor_result.scalars().first()
            if anchor_message is None:
                # Cold proactive nudge with no student message to anchor
                # to at all - nothing to generalize from, and nothing to
                # satisfy the FK with. The UI should disable the checkbox
                # in this case; this is the server-side backstop.
                raise ValueError("No student message in this conversation to anchor a reusable answer to.")

            # Whole-conversation context for the reconstruction call, not
            # just messages around a single question - same DESC-then-
            # reverse trick as the queue endpoint (DESC to get the most
            # RECENT rows, reversed after so the LLM reads it oldest-first).
            context_result = await db.execute(
                select(Message)
                .where(Message.college_id == college_id, Message.student_id == student_id)
                .order_by(Message.created_at.desc())
                .limit(SAVE_AS_ANSWER_CONTEXT_LIMIT)
            )
            recent_messages = list(reversed(context_result.scalars().all()))
            recent_conversation = "\n".join(f"{m.messager_role}: {m.content}" for m in recent_messages)

            reconstructed = reconstruct_staff_answer(recent_conversation, payload.content)

            resolved_at = datetime.utcnow()
            new_query = LowConfidenceQuery(
                college_id=college_id,
                student_id=student_id,
                question_message_id=anchor_message.message_id,
                answer_message_id=staff_message.message_id,
                similarity_score=None,
                resolved=True,
                resolved_by=staff_id,
                resolved_at=resolved_at,
            )
            db.add(new_query)
            await db.flush()  # need query.query_id for the chunk below, without committing yet

            embedder = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, api_key=settings.gemini_api_key, output_dimensionality=settings.vector_size)
            chunk_text = f"Question: {reconstructed.question}\nAnswer: {reconstructed.answer}"
            vector = embedder.embed_query(chunk_text)
            db.add(Chunk(college_id=college_id, chunk_content=chunk_text, embedding=vector, chunk_index=0, source_type="staff_answer", source_query_id=new_query.query_id, expires_at=payload.expires_at))

            # Counted in the same resolved-queries counter as a normal queue
            # reply, per how this was scoped - no separate origin tracking
            # for now. Resolution-time histogram is deliberately skipped:
            # flagged_at and resolved_at are the same instant here since
            # this was never actually flagged, so observing it would just
            # inject a stream of ~0-second entries into a histogram meant
            # to measure how long staff take to respond to real queue items.
            LOW_CONFIDENCE_QUERIES_RESOLVED.inc()
            await db.commit()

            saved_as_answer = True
            reconstructed_question = reconstructed.question
        except Exception:
            # The WhatsApp message already sent and saved successfully by
            # this point - a failure here (LLM error, embedding error,
            # whatever) shouldn't turn into a 500 for an already-successful
            # send. Roll back only the save-as-answer half, log it, and
            # tell the caller via the response instead of raising.
            await db.rollback()
            logger.error(f"save_as_answer failed for student_id={student_id}, message_id={staff_message.message_id}", exc_info=True)
            save_error = "Message sent, but saving it as a reusable answer failed. You can try again from the message box."

    return StudentMessageResponse(
        message_id=staff_message.message_id,
        student_id=staff_message.student_id,
        content=staff_message.content,
        created_at=staff_message.created_at,
        delivered=send_result["ok"],
        channel=send_result.get("channel", "text"),
        saved_as_answer=saved_as_answer,
        reconstructed_question=reconstructed_question,
        save_error=save_error,
    )


@router.patch("/{college_id}/{student_id}/notes")
async def update_student_notes(
    college_id: int,
    student_id: int,
    payload: StudentNotesUpdate,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # The column (internal_notes) and its display on StudentDetail already
    # existed - nothing ever wrote to it. This is that write path.
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student.internal_notes = payload.internal_notes
    await db.commit()

    return {"student_id": student_id, "internal_notes": student.internal_notes}


@router.patch("/{college_id}/{student_id}/assign")
async def assign_student(
    college_id: int,
    student_id: int,
    payload: StudentAssignUpdate,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    # Same situation as internal_notes: assigned_to and its FK to
    # staff_colleges were already in the schema, with nothing to set it.
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == student_id).limit(1))
    student = student_result.scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    assigned_staff_name = None
    if payload.assigned_to is not None:
        # Confirm the target staff member is actually part of this college -
        # without this check, one college's staff_id could get assigned a
        # student belonging to a different college, silently violating the
        # multi-tenant separation the rest of the app is careful about.
        staff_membership_result = await db.execute(
            select(StaffCollege)
            .where(StaffCollege.college_id == college_id, StaffCollege.staff_id == payload.assigned_to)
            .options(selectinload(StaffCollege.staff_member))
            .limit(1)
        )
        staff_membership = staff_membership_result.scalars().first()
        if not staff_membership:
            raise HTTPException(status_code=400, detail="That staff member isn't part of this college")
        assigned_staff_name = staff_membership.staff_member.staff_name

    student.assigned_to = payload.assigned_to
    await db.commit()

    return {"student_id": student_id, "assigned_to": student.assigned_to, "assigned_staff_name": assigned_staff_name}
