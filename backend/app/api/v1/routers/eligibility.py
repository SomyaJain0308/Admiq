from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.Course import Course
from backend.app.models.EligibilityRule import EligibilityRule
from backend.app.models.EligibilityEvent import EligibilityEvent
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.services.auth_services import verify_college_access
from backend.app.services import eligibility_service
from backend.app.schemas.eligibility import (
    RULE_CONFIG_MODELS,
    CourseCreate,
    CourseUpdate,
    CourseResponse,
    CourseDetailResponse,
    EligibilityRuleCreate,
    EligibilityRuleUpdate,
    EligibilityRuleResponse,
    RuleReorderRequest,
    CourseEligibilityStats,
    DropOffPoint,
    EligibilityAnalyticsResponse,
    RuleConflict,
    RuleConflictsResponse,
)

router = APIRouter(tags=["Eligibility"])


def _validate_rule_config(rule_type: str, config: dict) -> dict:
    # Rejects a config that doesn't match its rule_type's shape (e.g. a
    # min_percentage rule missing min_value) before it ever reaches the
    # WhatsApp flow, where a malformed config would otherwise surface as a
    # confusing runtime KeyError mid-conversation with a student.
    model = RULE_CONFIG_MODELS[rule_type]
    try:
        return model(**config).model_dump()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid config for rule_type '{rule_type}': {e.errors()}")


def _to_rule_response(rule: EligibilityRule) -> EligibilityRuleResponse:
    return EligibilityRuleResponse(
        rule_id=rule.rule_id,
        course_id=rule.course_id,
        rule_type=rule.rule_type,
        config=rule.config,
        order_index=rule.order_index,
        is_active=rule.is_active,
        generated_question=eligibility_service.describe_rule(rule),
    )


async def _get_course_or_404(db, college_id: int, course_id: int) -> Course:
    result = await db.execute(select(Course).where(Course.college_id == college_id, Course.course_id == course_id))
    course = result.scalars().first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found.")
    return course


async def _course_response(db, course: Course) -> CourseResponse:
    count_result = await db.execute(select(func.count()).select_from(EligibilityRule).where(EligibilityRule.course_id == course.course_id))
    return CourseResponse(
        course_id=course.course_id,
        college_id=course.college_id,
        course_name=course.course_name,
        parent_course_id=course.parent_course_id,
        is_published=course.is_published,
        order_index=course.order_index,
        admission_procedure=course.admission_procedure,
        rule_count=count_result.scalar_one(),
    )


async def _validate_parent_course_id(db, college_id: int, parent_course_id: int, exclude_course_id: int | None = None) -> None:
    """
    Shared guard for both create and update: the parent must be a real
    course at this same college (never another college's, even by guessing
    an id), and - for update only - moving a course under its own
    descendant would create a cycle the WhatsApp flow's parent-walk isn't
    built to detect at runtime (see _get_ancestor_chain's `seen` guard,
    which is a last-resort safety net, not something to rely on here).
    """
    result = await db.execute(select(Course).where(Course.college_id == college_id, Course.course_id == parent_course_id))
    parent = result.scalars().first()
    if parent is None:
        raise HTTPException(status_code=422, detail="parent_course_id must refer to an existing course at this college.")
    if exclude_course_id is None:
        return
    if parent_course_id == exclude_course_id:
        raise HTTPException(status_code=422, detail="A course can't be its own parent.")
    # Walk parent's own ancestor chain looking for exclude_course_id - if
    # found, exclude_course_id is a descendant of parent_course_id and
    # setting this parent would create a cycle.
    current = parent
    seen = {current.course_id}
    while current.parent_course_id is not None:
        if current.parent_course_id == exclude_course_id:
            raise HTTPException(status_code=422, detail="That would make a course its own ancestor - pick a different parent.")
        if current.parent_course_id in seen:
            break  # already-corrupt data; don't loop forever
        ancestor_result = await db.execute(select(Course).where(Course.college_id == college_id, Course.course_id == current.parent_course_id))
        current = ancestor_result.scalars().first()
        if current is None:
            break
        seen.add(current.course_id)


# --- Courses --------------------------------------------------------------

@router.get("/router/colleges/{college_id}/courses", response_model=list[CourseResponse])
async def list_courses(college_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    result = await db.execute(select(Course).where(Course.college_id == college_id).order_by(Course.order_index, Course.course_name))
    courses = result.scalars().all()
    return [await _course_response(db, c) for c in courses]


@router.post("/router/colleges/{college_id}/courses", response_model=CourseResponse, status_code=201)
async def create_course(college_id: int, payload: CourseCreate, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    if payload.parent_course_id is not None:
        await _validate_parent_course_id(db, college_id, payload.parent_course_id)
    max_order_result = await db.execute(select(func.max(Course.order_index)).where(Course.college_id == college_id))
    next_order = (max_order_result.scalar_one_or_none() or 0) + 1
    course = Course(college_id=college_id, course_name=payload.course_name, order_index=next_order, parent_course_id=payload.parent_course_id)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return await _course_response(db, course)


@router.get("/router/colleges/{college_id}/courses/{course_id}", response_model=CourseDetailResponse)
async def get_course(college_id: int, course_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    course = await _get_course_or_404(db, college_id, course_id)
    rules_result = await db.execute(select(EligibilityRule).where(EligibilityRule.college_id == college_id, EligibilityRule.course_id == course_id).order_by(EligibilityRule.order_index))
    rules = rules_result.scalars().all()
    base = await _course_response(db, course)

    inherited_rules = []
    programme_path = None
    if course.parent_course_id is not None:
        effective = await eligibility_service.get_effective_rules(db, college_id, course)
        inherited_rules = [r for r in effective if r.course_id != course.course_id]
        programme_path = await eligibility_service.programme_path(db, college_id, course)

    return CourseDetailResponse(
        **base.model_dump(),
        rules=[_to_rule_response(r) for r in rules],
        inherited_rules=[_to_rule_response(r) for r in inherited_rules],
        programme_path=programme_path,
    )


@router.patch("/router/colleges/{college_id}/courses/{course_id}", response_model=CourseResponse)
async def update_course(college_id: int, course_id: int, payload: CourseUpdate, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    course = await _get_course_or_404(db, college_id, course_id)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("parent_course_id") is not None:
        await _validate_parent_course_id(db, college_id, updates["parent_course_id"], exclude_course_id=course_id)
    for field, value in updates.items():
        setattr(course, field, value)
    await db.commit()
    await db.refresh(course)
    return await _course_response(db, course)


@router.delete("/router/colleges/{college_id}/courses/{course_id}", status_code=204)
async def delete_course(college_id: int, course_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    course = await _get_course_or_404(db, college_id, course_id)
    await db.delete(course)  # cascades to eligibility_rules
    await db.commit()


# --- Eligibility rules ------------------------------------------------------

@router.post("/router/colleges/{college_id}/courses/{course_id}/rules", response_model=EligibilityRuleResponse, status_code=201)
async def create_rule(college_id: int, course_id: int, payload: EligibilityRuleCreate, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    await _get_course_or_404(db, college_id, course_id)  # 404 before touching rules if the course doesn't exist/isn't this college's
    validated_config = _validate_rule_config(payload.rule_type, payload.config)

    max_order_result = await db.execute(select(func.max(EligibilityRule.order_index)).where(EligibilityRule.course_id == course_id))
    next_order = (max_order_result.scalar_one_or_none() or 0) + 1

    rule = EligibilityRule(college_id=college_id, course_id=course_id, rule_type=payload.rule_type, config=validated_config, is_active=payload.is_active, order_index=next_order)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_rule_response(rule)


async def _get_rule_or_404(db, college_id: int, course_id: int, rule_id: int) -> EligibilityRule:
    result = await db.execute(select(EligibilityRule).where(EligibilityRule.college_id == college_id, EligibilityRule.course_id == course_id, EligibilityRule.rule_id == rule_id))
    rule = result.scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Eligibility rule not found.")
    return rule


@router.patch("/router/colleges/{college_id}/courses/{course_id}/rules/{rule_id}", response_model=EligibilityRuleResponse)
async def update_rule(college_id: int, course_id: int, rule_id: int, payload: EligibilityRuleUpdate, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    rule = await _get_rule_or_404(db, college_id, course_id, rule_id)
    if payload.config is not None:
        rule.config = _validate_rule_config(rule.rule_type, payload.config)
    if payload.is_active is not None:
        rule.is_active = payload.is_active
    await db.commit()
    await db.refresh(rule)
    return _to_rule_response(rule)


@router.delete("/router/colleges/{college_id}/courses/{course_id}/rules/{rule_id}", status_code=204)
async def delete_rule(college_id: int, course_id: int, rule_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    rule = await _get_rule_or_404(db, college_id, course_id, rule_id)
    await db.delete(rule)
    await db.commit()


@router.post("/router/colleges/{college_id}/courses/{course_id}/rules/reorder", response_model=list[EligibilityRuleResponse])
async def reorder_rules(college_id: int, course_id: int, payload: RuleReorderRequest, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    # The flow asks rules in order_index order and stops at the first
    # failure, so staff dragging a rule to the top of the list is a real,
    # meaningful change to student experience - not just cosmetic.
    result = await db.execute(select(EligibilityRule).where(EligibilityRule.college_id == college_id, EligibilityRule.course_id == course_id))
    rules_by_id = {r.rule_id: r for r in result.scalars().all()}

    if set(payload.rule_ids) != set(rules_by_id.keys()):
        raise HTTPException(status_code=400, detail="rule_ids must include exactly every rule belonging to this course, no more and no less.")

    for index, rule_id in enumerate(payload.rule_ids):
        rules_by_id[rule_id].order_index = index

    await db.commit()
    ordered = sorted(rules_by_id.values(), key=lambda r: r.order_index)
    for r in ordered:
        await db.refresh(r)
    return [_to_rule_response(r) for r in ordered]


# --- Preview ----------------------------------------------------------------

@router.get("/router/colleges/{college_id}/courses/{course_id}/preview")
async def preview_course_flow(college_id: int, course_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """
    A lightweight sanity-check for staff building a course's rules: the
    ordered list of questions a student would actually be asked, in plain
    English, without needing to run the real WhatsApp wizard end to end.

    Uses the same effective-rules merge the real WhatsApp flow uses (own
    rules plus every ancestor's, for a branch course under a programme
    type) rather than just this course's own rules - otherwise a preview of
    a branch would silently miss whatever's inherited from its parent and
    give staff a false picture of what students are actually asked.
    """
    course = await _get_course_or_404(db, college_id, course_id)
    rules = await eligibility_service.get_effective_rules(db, college_id, course)

    steps = [f"1. Ask which course - the student would see \"{course.course_name}\" in the list."]
    if eligibility_service.requires_category(rules):
        steps.append("2. Ask reservation category (General / OBC / SC / ST / EWS / Other).")
    for i, rule in enumerate(rules, start=1):
        inherited_note = " (inherited from a parent programme)" if rule.course_id != course.course_id else ""
        steps.append(f"{i + 1}. {eligibility_service.describe_rule(rule)}{inherited_note}")
    steps.append(f"{len(steps) + 1}. If all pass: congratulate the student and offer to flag them for admission-procedure info.")

    return {"course_name": course.course_name, "is_published": course.is_published, "steps": steps}


# --- Rule conflicts -----------------------------------------------------

@router.get("/router/colleges/{college_id}/courses/{course_id}/rule-conflicts", response_model=RuleConflictsResponse)
async def get_rule_conflicts(college_id: int, course_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """
    Sanity-check a course's rule set for combinations that are individually
    valid (already passed RULE_CONFIG_MODELS at create/update time) but
    don't work together - see eligibility_service.find_rule_conflicts for
    exactly what's checked. Uses the same effective-rules merge the real
    WhatsApp flow and the /preview endpoint use, so a branch course is
    checked against what students are actually asked, inherited rules
    included - not just this course's own.
    """
    course = await _get_course_or_404(db, college_id, course_id)
    rules = await eligibility_service.get_effective_rules(db, college_id, course)
    conflicts = eligibility_service.find_rule_conflicts(rules)
    return RuleConflictsResponse(conflicts=[RuleConflict(**c) for c in conflicts])


# --- Analytics ------------------------------------------------------------

@router.get("/router/colleges/{college_id}/eligibility-analytics", response_model=EligibilityAnalyticsResponse)
async def get_eligibility_analytics(college_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    """
    College-wide view built on eligibility_events (see
    models/EligibilityEvent.py, written by eligibility_service.py's
    _record_eligibility_event): pass/fail rate per course, and exactly
    where students give up (which course, which step, and - for a rule
    question - which one). Student.profile_signals alone can't answer
    either question: it only keeps each student's own last 10 checks and
    never records a cancel/timeout at all.
    """
    outcome_rows = (
        await db.execute(
            select(EligibilityEvent.course_id, Course.course_name, EligibilityEvent.outcome, func.count())
            .join(Course, and_(Course.college_id == EligibilityEvent.college_id, Course.course_id == EligibilityEvent.course_id))
            .where(EligibilityEvent.college_id == college_id, EligibilityEvent.outcome.in_(("passed", "failed", "borderline")))
            .group_by(EligibilityEvent.course_id, Course.course_name, EligibilityEvent.outcome)
        )
    ).all()

    stats_by_course: dict[int, dict] = {}
    for course_id, course_name, outcome, count in outcome_rows:
        entry = stats_by_course.setdefault(course_id, {"course_id": course_id, "course_name": course_name, "passed": 0, "failed": 0, "borderline": 0})
        entry[outcome] = count

    course_stats = []
    for entry in stats_by_course.values():
        total = entry["passed"] + entry["failed"] + entry["borderline"]
        course_stats.append(CourseEligibilityStats(course_id=entry["course_id"], course_name=entry["course_name"], passed=entry["passed"], failed=entry["failed"], borderline=entry["borderline"], total_completed=total, pass_rate=(entry["passed"] / total) if total else 0.0))
    course_stats.sort(key=lambda c: c.total_completed, reverse=True)

    dropoff_rows = (
        await db.execute(
            select(EligibilityEvent.course_id, EligibilityEvent.step, EligibilityEvent.rule_index, func.count())
            .where(EligibilityEvent.college_id == college_id, EligibilityEvent.outcome.in_(("cancelled", "timed_out")))
            .group_by(EligibilityEvent.course_id, EligibilityEvent.step, EligibilityEvent.rule_index)
        )
    ).all()

    course_ids = {course_id for course_id, _, _, _ in dropoff_rows if course_id is not None}
    courses_by_id: dict[int, Course] = {}
    if course_ids:
        result = await db.execute(select(Course).where(Course.college_id == college_id, Course.course_id.in_(course_ids)))
        courses_by_id = {c.course_id: c for c in result.scalars().all()}

    # Lazily resolve a rule_index to a human-readable description, per
    # course, using each course's CURRENT effective (own + inherited) rule
    # list in the same order the flow itself asks them - the same ordering
    # "Question X of Y" numbers against. If the rule list has changed since
    # (reordered, added to, or a rule removed) enough that the index no
    # longer lines up with anything, this just comes back None rather than
    # guessing - a stale label would be worse than no label.
    rule_descriptions_by_course: dict[int, list[str]] = {}

    async def _rule_description(course_id: int | None, rule_index: int | None) -> str | None:
        if course_id is None or rule_index is None:
            return None
        if course_id not in rule_descriptions_by_course:
            course = courses_by_id.get(course_id)
            if course is None:
                rule_descriptions_by_course[course_id] = []
            else:
                effective_rules = await eligibility_service.get_effective_rules(db, college_id, course)
                rule_descriptions_by_course[course_id] = [eligibility_service.describe_rule(r) for r in effective_rules]
        descriptions = rule_descriptions_by_course[course_id]
        return descriptions[rule_index] if 0 <= rule_index < len(descriptions) else None

    drop_off_points = []
    for course_id, step, rule_index, count in dropoff_rows:
        course = courses_by_id.get(course_id) if course_id is not None else None
        drop_off_points.append(DropOffPoint(course_id=course_id, course_name=course.course_name if course else None, step=step, rule_index=rule_index, rule_description=await _rule_description(course_id, rule_index), drop_offs=count))
    drop_off_points.sort(key=lambda d: d.drop_offs, reverse=True)

    return EligibilityAnalyticsResponse(course_stats=course_stats, drop_off_points=drop_off_points)
