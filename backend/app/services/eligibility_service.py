"""
The WhatsApp eligibility-checker flow.

Deliberately separate from rag/agent.py for the pass/fail decision itself:
eligibility has real stakes for a student's application, so it's driven by
staff-configured structured rules (Course/EligibilityRule) and a scripted
state machine, not an LLM inferring an answer from a brochure PDF. It's
routed to from whatsapp_chat.py *before* the agent is ever invoked, whenever
a student triggers it or already has an active flow in progress.

The one exception is await_procedure_interest: once eligibility itself is
already decided, asking the RAG agent what a college's own brochure/RAG
index says about its admission procedure (see _ask_rag_about_procedure) is
just an ordinary Q&A lookup, not a new pass/fail call - so that one step
optionally takes an `agent` (threaded through handle_incoming_message) and
falls back to the old "not available yet" + human flag if it isn't passed
in, errors, or comes back empty.

Flow state lives in StudentSession.active_flow (JSONB) so one process can
answer a message using nothing but the DB row - no separate session cache.

State machine (flow == "eligibility_check"):
  await_start_confirm      -> ambiguous trigger; confirming before committing to the flow
  await_course             -> student is looking at the course list
  await_category           -> course needs a reservation category first
  await_summary_confirm    -> course (+ category) chosen; confirming before rules are scored
  await_rule                -> student is mid-way through the ordered rule list
  await_procedure_interest -> eligible; asking if they want admission-procedure info
  await_another_course     -> asking whether to check a different course
(No row / flow is None -> ordinary free-chat, handled by the RAG agent.)

Mistake correction: every step from await_course onward pushes a snapshot of
the step it's leaving onto flow["history"] before moving forward. Typing
"back" (or tapping the id in BUTTON_BACK, wired up on the summary-confirm
prompt) pops the last snapshot and re-renders that step via _render_step, so
a wrong tap or a fat-fingered course/category is one word to fix instead of
a full `cancel` + redo. This is deliberately just a rewind, not a jump to an
arbitrary earlier step: going back always resumes at exactly the last thing
that was answered, and answering it again silently discards whatever
forward path had been built past that point (the usual back+redo pattern).
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import select

from backend.app.models.Course import Course
from backend.app.models.EligibilityRule import EligibilityRule
from backend.app.models.EligibilityEvent import EligibilityEvent

logger = logging.getLogger(__name__)

FLOW_NAME = "eligibility_check"

# Fixed WhatsApp interactive-reply ids the flow recognizes. A button in a
# future welcome/menu message with this id would also start the flow with no
# text-matching needed at all - see is_trigger below.
BUTTON_START = "start_eligibility_check"
MAX_LIST_ROWS = 10  # WhatsApp's own hard limit on a single list message

# How long a flow can sit untouched (student went quiet mid-flow) before the
# *next* message - whatever it's about - gets reset to free chat instead of
# being force-fed into a stale question. Without this, StudentSession.
# active_flow has no expiry of its own and a student who goes quiet for days
# comes back to find an unrelated message answered as if it were a tap on a
# "Yes/No" button from a check they've long forgotten.
FLOW_IDLE_TIMEOUT_MINUTES = 30

# Rule types that ask about a numeric threshold (percentage, rank,
# percentile...) rather than a fixed fact (stream) or a staff-authored
# arbitrary question (custom_yesno). Only these offer the third "Close / not
# sure" button below - "close" doesn't mean anything for "did you study
# PCM?" or a yes/no staff wrote themselves.
NUMERIC_RULE_TYPES = ("min_percentage", "min_subject_marks", "entrance_cutoff", "category_cutoff")
BUTTON_CLOSE = "rule_close"

# Id for the one explicit "back" button (on the summary-confirm prompt, the
# only step with room for a third button - see build_rule_prompt/
# _summary_prompt). Everywhere else "back" is typed, same as cancel/stop/
# menu/exit, since WhatsApp button messages cap at 3 buttons and numeric
# rules already use all 3 (Yes/No/Close).
BUTTON_BACK = "flow_back"

CATEGORY_LABELS = {
    "general": "General",
    "obc": "OBC",
    "sc": "SC",
    "st": "ST",
    "ews": "EWS",
    "other": "Other / not sure",
}


# --------------------------------------------------------------------------
# Trigger detection
# --------------------------------------------------------------------------

# Short, direct phrasings that essentially only ever mean "I want an
# eligibility check" - safe to start the flow on immediately. "eligib" as a
# bare substring covers eligible/eligibility/ineligible/not eligible/etc.
# without listing every inflection.
_STRONG_TRIGGER_PHRASES = (
    "eligib",
    "am i qualified",
    "do i qualify",
    "check my qualification",
)

# Softer signals that often mean the same thing but also show up in
# unrelated questions ("is there a scholarship I qualify for", "what's the
# fee cutoff date") or are asked about something this flow doesn't cover
# (financial aid, hostel seats). Matching one of these still routes into the
# flow (see is_trigger) but - unlike a strong match - doesn't start it
# outright; _trigger_confidence marks it "weak" so handle_incoming_message
# asks a one-tap confirmation first instead of assuming and hijacking
# whatever the student was actually asking about.
_WEAK_TRIGGER_PHRASES = (
    "qualify", "qualified", "qualification",
    "cutoff", "cut off", "cut-off",
    "admission criteria", "admission requirement",
    "meet the requirement", "meet the criteria",
    "minimum marks required", "minimum percentage required",
)

# A plain substring check on "eligib" misses common typos ("eligiblty",
# "eligable", "elgibility") entirely, so those fall through to the RAG agent
# with no idea what's being asked. Fuzzy-matching against this one root -
# rather than hand-maintaining a typo list - catches most of them; treated
# as "weak" (confirm first) since a fuzzy match is inherently less certain
# than an exact one.
_ELIGIBILITY_ROOT = "eligib"
_FUZZY_MIN_WORD_LEN = 6
_FUZZY_MATCH_THRESHOLD = 0.68


def _fuzzy_contains_eligibility_typo(normalized: str) -> bool:
    root_len = len(_ELIGIBILITY_ROOT)
    for word in re.findall(r"[a-z]+", normalized):
        if len(word) < _FUZZY_MIN_WORD_LEN:
            continue
        # Try a couple of prefix lengths around the root's own length - a
        # single fixed slice misses typos that add/drop a character early
        # ("elgibility" vs "eligibility") since that shifts everything after
        # the drop out of a same-length window.
        best_ratio = max(SequenceMatcher(None, word[:n], _ELIGIBILITY_ROOT).ratio() for n in (root_len - 1, root_len, root_len + 1, root_len + 2))
        if best_ratio >= _FUZZY_MATCH_THRESHOLD:
            return True
    return False


def _trigger_confidence(content: str, message_type: str) -> str | None:
    """
    "strong" -> start the flow immediately. "weak" -> route into the flow
    but confirm with the student first (see await_start_confirm). None ->
    not a trigger at all; goes to the RAG agent as ordinary free chat.
    """
    if message_type in ("interactive_button", "interactive_list"):
        return "strong" if content == BUTTON_START else None

    normalized = (content or "").strip().lower()
    if not normalized:
        return None
    if any(p in normalized for p in _STRONG_TRIGGER_PHRASES):
        return "strong"
    if any(p in normalized for p in _WEAK_TRIGGER_PHRASES):
        return "weak"
    if _fuzzy_contains_eligibility_typo(normalized):
        return "weak"
    return None


def is_trigger(content: str, message_type: str) -> bool:
    """
    Whether an incoming message (that isn't already inside a flow) should be
    routed into the eligibility flow at all. Both "strong" and "weak"
    confidence route here - see _trigger_confidence and
    handle_incoming_message for how a "weak" match then gets a one-tap
    confirmation instead of immediately taking over the conversation.
    """
    return _trigger_confidence(content, message_type) is not None


def _is_cancel(content: str, message_type: str) -> bool:
    if message_type != "text":
        return False
    return (content or "").strip().lower() in ("cancel", "stop", "menu", "exit")


def _is_back(content: str, message_type: str) -> bool:
    if message_type == "interactive_button":
        return content == BUTTON_BACK
    if message_type != "text":
        return False
    return (content or "").strip().lower() in ("back", "go back", "previous")


def _is_flow_expired(flow: dict) -> bool:
    """
    Whether an in-progress flow has been idle long enough that the next
    message shouldn't be force-fed into it as an answer to a question the
    student has likely forgotten was even asked. `updated_at` is stamped by
    _base_result on every step; a flow saved before this field existed (or
    with a malformed value) is treated as not expired rather than raising,
    since failing safe here just means one extra stale re-prompt, not a
    broken flow.
    """
    updated_at = flow.get("updated_at")
    if not updated_at:
        return False
    try:
        last_touched = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    if last_touched.tzinfo is None:
        last_touched = last_touched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last_touched) > timedelta(minutes=FLOW_IDLE_TIMEOUT_MINUTES)


# --------------------------------------------------------------------------
# Rule -> question, and answer -> pass/fail
# --------------------------------------------------------------------------

def requires_category(rules: list[EligibilityRule]) -> bool:
    return any(r.rule_type == "category_cutoff" for r in rules)


def find_rule_conflicts(rules: list[EligibilityRule]) -> list[dict]:
    """
    Sanity checks beyond RULE_CONFIG_MODELS' per-rule shape validation (see
    schemas/eligibility.py) - things that are only wrong as a *combination*
    of otherwise-valid rules. Meant to be called with a single course's own
    rules, or get_effective_rules' merged list for a branch course, since a
    conflict can span an inherited rule and a course's own.

    Deliberately cheap/heuristic (same philosophy as the rest of this flow -
    see module docstring), not exhaustive: catches the mistakes staff
    actually make - forgetting a category, pasting two thresholds for the
    same thing, two mutually-exclusive stream rules - not every
    theoretically possible contradiction. Returns a list of
    {"severity": "error"|"warning", "rule_ids": [...], "message": str}
    dicts (matching schemas/eligibility.py's RuleConflict) rather than
    Pydantic objects directly, so this module doesn't need to import the
    schema layer.
    """
    conflicts: list[dict] = []
    active = [r for r in rules if r.is_active]

    # 1. category_cutoff coverage - a reservation category the WhatsApp
    # flow can actually present (CATEGORY_LABELS) but this rule's
    # thresholds don't mention falls back to "general", or - worse - to an
    # arbitrary dict-order pick if there's no "general" either (see
    # _resolve_category_threshold).
    for rule in active:
        if rule.rule_type != "category_cutoff":
            continue
        thresholds = rule.config.get("thresholds", {})
        missing = [k for k in CATEGORY_LABELS if k not in thresholds]
        if not missing:
            continue
        missing_labels = ", ".join(CATEGORY_LABELS.get(k, k) for k in missing)
        if "general" not in thresholds:
            conflicts.append({"severity": "error", "rule_ids": [rule.rule_id], "message": f"This rule has no \"general\" threshold and doesn't cover: {missing_labels}. A student in one of those categories gets an arbitrary threshold instead of a sensible fallback."})
        else:
            conflicts.append({"severity": "warning", "rule_ids": [rule.rule_id], "message": f"This rule doesn't have a specific threshold for: {missing_labels} - those students fall back to the \"general\" threshold. Confirm that's intended."})

    # 2. Redundant/contradictory numeric thresholds - two active rules
    # really about the same underlying measurement with different cutoffs.
    # Not necessarily a bug (staff might genuinely want the stricter one to
    # win) but worth a look, since it's more often a leftover duplicate.
    def _numeric_key_and_value(rule: EligibilityRule):
        c = rule.config
        if rule.rule_type == "min_percentage":
            return ("min_percentage", c.get("label", "").strip().lower()), c.get("min_value")
        if rule.rule_type == "min_subject_marks":
            return ("min_subject_marks", c.get("subject", "").strip().lower()), c.get("min_value")
        if rule.rule_type == "entrance_cutoff":
            return ("entrance_cutoff", c.get("exam_name", "").strip().lower(), c.get("metric")), c.get("threshold")
        return None, None

    seen_by_key: dict[tuple, tuple[EligibilityRule, float]] = {}
    for rule in active:
        key, value = _numeric_key_and_value(rule)
        if key is None:
            continue
        earlier = seen_by_key.get(key)
        if earlier is None:
            seen_by_key[key] = (rule, value)
            continue
        earlier_rule, earlier_value = earlier
        conflicts.append({"severity": "warning", "rule_ids": [earlier_rule.rule_id, rule.rule_id], "message": f"Two active rules both check {key[1]!r} with different thresholds ({earlier_value} vs {value}) - only the stricter one can ever matter; the other is dead weight."})

    # 3. Mutually-exclusive stream requirements - two required_stream rules
    # whose allowed sets don't overlap at all mean literally no student can
    # pass both, so nobody can ever pass this course's check.
    stream_rules = [r for r in active if r.rule_type == "required_stream"]
    for i in range(len(stream_rules)):
        for j in range(i + 1, len(stream_rules)):
            a, b = stream_rules[i], stream_rules[j]
            set_a = {s.strip().lower() for s in a.config.get("allowed_streams", [])}
            set_b = {s.strip().lower() for s in b.config.get("allowed_streams", [])}
            if set_a and set_b and set_a.isdisjoint(set_b):
                conflicts.append({"severity": "error", "rule_ids": [a.rule_id, b.rule_id], "message": "Two active \"required stream\" rules with no overlapping streams - no student can ever satisfy both, so nobody can pass this course's check."})

    return conflicts


def _resolve_category_threshold(config: dict, category: str | None):
    """
    Single source of truth for which threshold a category_cutoff rule
    applies to a given student. Falls back to the "general" threshold (not
    an arbitrary dict-ordering pick) when the student's category isn't a key
    in `thresholds` - covers both category=None (asked before we know it)
    and a category like "other" that staff didn't configure a bespoke
    cutoff for. Raises if there's truly nothing to fall back to, since that
    means the rule was saved without a usable default and staff need to fix it.
    """
    thresholds = config["thresholds"]
    if category and category in thresholds:
        return thresholds[category]
    if "general" in thresholds:
        return thresholds["general"]
    return next(iter(thresholds.values()))


def describe_rule(rule: EligibilityRule, category: str | None = None) -> str:
    """
    Human-readable summary of a rule. Without `category` (the staff
    dashboard preview case) a category_cutoff rule is described in full,
    listing every configured threshold since there's no one student to
    resolve it for. With `category` (the WhatsApp flow, once we know the
    student's category) it's described as the single threshold that
    actually applied to them - used for the "here's what you didn't meet"
    failure message.
    """
    c = rule.config
    if rule.rule_type == "min_percentage":
        return f"{c['label']} must be {c['min_value']}% or above"
    if rule.rule_type == "min_subject_marks":
        return f"{c['subject']} marks must be {c['min_value']}% or above"
    if rule.rule_type == "required_stream":
        return f"Stream must be one of: {', '.join(c['allowed_streams'])}"
    if rule.rule_type == "entrance_cutoff":
        comparator = "or above" if c.get("metric") == "percentile" else "or better (lower)"
        return f"{c['exam_name']} {c.get('metric', 'percentile')} must be {c['threshold']} {comparator}"
    if rule.rule_type == "category_cutoff":
        direction = "or above" if c.get("higher_is_better", True) else "or below"
        if category is not None:
            threshold = _resolve_category_threshold(c, category)
            return f"{c['metric_label']} must be {threshold} {direction}"
        parts = ", ".join(f"{CATEGORY_LABELS.get(k, k)}: {v}" for k, v in c["thresholds"].items())
        return f"{c['metric_label']} {direction} ({parts})"
    if rule.rule_type == "custom_yesno":
        return f"\"{c['question']}\" (passes on {c['pass_answer']})"
    return "Unrecognized rule"


def _with_rule_progress(prompt: dict, rule_index: int, total_rules: int) -> dict:
    """
    Prepend a "Question X of Y" progress line onto a rule prompt's body, so
    a student mid-flow has a sense of how much is left. Applied at every
    place a rule prompt gets shown (first ask, a "back" re-render, and the
    "please tap one of the options above" retry) rather than baked into
    build_rule_prompt itself, since that function only knows about one
    rule - not its position in the course's full rule list.
    """
    return {**prompt, "body": f"Question {rule_index + 1} of {total_rules}\n{prompt['body']}"}


def build_rule_prompt(rule: EligibilityRule, category: str | None) -> dict:
    """
    Turn one EligibilityRule into a WhatsApp interactive payload (see
    send_whatsapp_interactive_message). Every rule type resolves to either a
    yes/no(/close) button question or a short list selection. Numeric rule
    types (NUMERIC_RULE_TYPES) get a third "Close / not sure" button since a
    flat No there could just as easily be a confident fail or a genuine "I'm
    a couple points off and don't know" - see evaluate_rule_reply.
    """
    c = rule.config

    if rule.rule_type == "required_stream":
        rows = [{"id": f"stream_{s.lower().replace(' ', '_')}", "title": s[:24]} for s in c["allowed_streams"][:MAX_LIST_ROWS]]
        return {"type": "list", "body": "Which stream did you study in 12th?", "button_label": "Select stream", "section_title": "Streams", "rows": rows}

    if rule.rule_type == "category_cutoff":
        threshold = _resolve_category_threshold(c, category)
        direction = "or above" if c.get("higher_is_better", True) else "or below"
        question = f"Is your {c['metric_label']} {threshold} {direction}?"
        return _yes_no_prompt(question, allow_close=True)

    if rule.rule_type == "min_percentage":
        return _yes_no_prompt(f"Is your {c['label']} {c['min_value']}% or above?", allow_close=True)

    if rule.rule_type == "min_subject_marks":
        return _yes_no_prompt(f"Is your {c['subject']} score {c['min_value']}% or above?", allow_close=True)

    if rule.rule_type == "entrance_cutoff":
        if c.get("metric") == "rank":
            question = f"Is your {c['exam_name']} rank {int(c['threshold'])} or better (i.e. that number or lower)?"
        else:
            question = f"Is your {c['exam_name']} percentile {c['threshold']} or above?"
        return _yes_no_prompt(question, allow_close=True)

    if rule.rule_type == "custom_yesno":
        return _yes_no_prompt(c["question"])

    raise ValueError(f"Unknown rule_type: {rule.rule_type}")


def _yes_no_prompt(question: str, allow_close: bool = False) -> dict:
    buttons = [{"id": "rule_yes", "title": "Yes"}, {"id": "rule_no", "title": "No"}]
    if allow_close:
        buttons.append({"id": BUTTON_CLOSE, "title": "Close / not sure"})
    return {"type": "button", "body": question, "buttons": buttons}


def evaluate_rule_reply(rule: EligibilityRule, content: str, message_type: str) -> bool | str | None:
    """
    True/False if the reply resolves this rule, the string "borderline" if
    the student tapped/typed "close / not sure" (only offered for
    NUMERIC_RULE_TYPES - see build_rule_prompt), or None if it doesn't match
    what was asked (caller should re-prompt). Covers both a tapped
    button/list row and typed text for accessibility.
    """
    c = rule.config
    normalized = (content or "").strip().lower()

    if rule.rule_type == "required_stream":
        chosen = None
        if message_type == "interactive_list" and content.startswith("stream_"):
            chosen = content[len("stream_"):]
        else:
            for s in c["allowed_streams"]:
                if s.lower() == normalized:
                    chosen = s.lower().replace(" ", "_")
                    break
        if chosen is None:
            return None
        return any(s.lower().replace(" ", "_") == chosen for s in c["allowed_streams"])

    allow_close = rule.rule_type in NUMERIC_RULE_TYPES
    close_phrases = ("close", "not sure", "unsure", "maybe", "close / not sure", "close/not sure", "don't know", "dont know")

    # Every other rule type is a yes/no(/close) question.
    if message_type == "interactive_button" and content == BUTTON_CLOSE:
        return "borderline" if allow_close else None
    if message_type == "interactive_button" and content in ("rule_yes", "rule_no"):
        answer = "yes" if content == "rule_yes" else "no"
    elif allow_close and normalized in close_phrases:
        return "borderline"
    elif normalized in ("yes", "no", "y", "n"):
        answer = "yes" if normalized in ("yes", "y") else "no"
    else:
        return None

    pass_answer = c.get("pass_answer", "yes") if rule.rule_type == "custom_yesno" else "yes"
    return answer == pass_answer


def parse_category_reply(content: str, message_type: str) -> str | None:
    if message_type == "interactive_list" and content.startswith("cat_"):
        key = content[len("cat_"):]
        return key if key in CATEGORY_LABELS else None
    normalized = (content or "").strip().lower()
    for key, label in CATEGORY_LABELS.items():
        if label.lower() == normalized or key == normalized:
            return key
    return None


_COURSE_NAME_FUZZY_THRESHOLD = 0.72


def _fuzzy_match_course_name(normalized: str, courses: list[Course]) -> Course | None:
    """
    Typed-name fallback beyond an exact match - reuses the same
    difflib-based approach as _fuzzy_contains_eligibility_typo above. Lets a
    close typed guess ("b.tech cse" for "B.Tech in CSE") still resolve
    instead of failing silently back to "please pick from the list", which
    matters more now that a branch list can still exceed 10 rows even with
    programme-type grouping in place.
    """
    if not normalized:
        return None
    best_course, best_ratio = None, 0.0
    for c in courses:
        ratio = SequenceMatcher(None, normalized, c.course_name.strip().lower()).ratio()
        if ratio > best_ratio:
            best_course, best_ratio = c, ratio
    return best_course if best_ratio >= _COURSE_NAME_FUZZY_THRESHOLD else None


def parse_course_reply(content: str, message_type: str, courses: list[Course]) -> Course | None:
    if message_type == "interactive_list" and content.startswith("course_"):
        try:
            course_id = int(content[len("course_"):])
        except ValueError:
            return None
        return next((c for c in courses if c.course_id == course_id), None)
    normalized = (content or "").strip().lower()
    if not normalized:
        return None
    exact = next((c for c in courses if c.course_name.strip().lower() == normalized), None)
    if exact is not None:
        return exact
    return _fuzzy_match_course_name(normalized, courses)


# --------------------------------------------------------------------------
# Prompt builders for the non-rule steps
# --------------------------------------------------------------------------

def _course_list_prompt(courses: list[Course], parent_name: str | None = None) -> dict:
    rows = [{"id": f"course_{c.course_id}", "title": c.course_name[:24]} for c in courses[:MAX_LIST_ROWS]]
    if len(courses) > MAX_LIST_ROWS:
        # A programme type (e.g. a huge "B.Tech" with 15 specializations)
        # can still exceed WhatsApp's 10-row cap even after grouping - the
        # typed-name fuzzy fallback (parse_course_reply) is the safety net
        # for that rare case, so this stays a soft cap rather than needing
        # pagination.
        logger.warning("Course list for parent_name=%r has more than %d published entries; only the first %d are shown.", parent_name, MAX_LIST_ROWS, MAX_LIST_ROWS)
    if parent_name:
        question = f"Which {parent_name} programme would you like to check eligibility for?"
    else:
        question = "Which course would you like to check eligibility for?"
    body = f"{question}\n\nDon't see it? Just type its name."
    return {"type": "list", "body": body, "button_label": "Select course", "section_title": "Courses", "rows": rows}


def _category_prompt() -> dict:
    rows = [{"id": f"cat_{k}", "title": v} for k, v in CATEGORY_LABELS.items()]
    return {"type": "list", "body": "Which reservation category do you belong to? This affects the cutoff.", "button_label": "Select category", "section_title": "Category", "rows": rows}


def _summary_prompt(course_name: str, category: str | None, programme_path: str | None = None) -> dict:
    lines = []
    if programme_path:
        lines.append(f"Programme: {programme_path}")
    lines.append(f"Course: {course_name}")
    if category:
        lines.append(f"Category: {CATEGORY_LABELS.get(category, category)}")
    body = "Just to confirm before I check the requirements:\n\n" + "\n".join(lines) + "\n\nShall I go ahead?"
    return {
        "type": "button",
        "body": body,
        "buttons": [{"id": "summary_confirm_yes", "title": "Yes, check"}, {"id": BUTTON_BACK, "title": "Go back"}],
    }


def _procedure_interest_prompt(course_name: str) -> dict:
    return {"type": "button", "body": f"Good news - you meet the eligibility criteria for {course_name}! Would you like to know the admission procedure?", "buttons": [{"id": "proc_yes", "title": "Yes"}, {"id": "proc_no", "title": "No"}]}


def _another_course_prompt() -> dict:
    return {"type": "button", "body": "Would you like to check eligibility for another course?", "buttons": [{"id": "another_yes", "title": "Yes"}, {"id": "another_no", "title": "No"}]}


def render_interactive_as_text(interactive: dict) -> str:
    """Flattened text version of an interactive payload, for the message transcript staff see in the dashboard (which only stores plain text)."""
    if interactive["type"] == "button":
        options = " / ".join(f"[{b['title']}]" for b in interactive["buttons"])
    else:
        options = " / ".join(f"[{r['title']}]" for r in interactive["rows"])
    return f"{interactive['body']}\n{options}"


# --------------------------------------------------------------------------
# Course/rule lookups
# --------------------------------------------------------------------------

async def _get_published_courses(db, college_id: int, parent_id: int | None = None) -> list[Course]:
    """
    Published courses at one level of the hierarchy: the top level when
    parent_id is None (a mix of standalone courses and programme-type
    nodes), or one programme type's published branches when parent_id is a
    course_id. Comparing to a Python `None` here produces an `IS NULL`
    check, not a no-op, so this one query serves both cases.
    """
    result = await db.execute(select(Course).where(Course.college_id == college_id, Course.is_published == True, Course.parent_course_id == parent_id).order_by(Course.order_index, Course.course_name))  # noqa: E712
    return list(result.scalars().all())


async def _has_published_children(db, college_id: int, course_id: int) -> bool:
    """
    Whether tapping this course should drill into its branches instead of
    treating it as a final, checkable selection - see _handle_await_course.
    """
    result = await db.execute(select(Course.course_id).where(Course.college_id == college_id, Course.parent_course_id == course_id, Course.is_published == True).limit(1))  # noqa: E712
    return result.scalars().first() is not None


async def _get_ancestor_chain(db, college_id: int, course: Course) -> list[Course]:
    """
    Root-to-immediate-parent chain above `course` (not including `course`
    itself), by walking parent_course_id up one row at a time. `seen`
    guards against an accidental cycle (which validation on write should
    prevent, but a corrupt/hand-edited row shouldn't be able to hang this in
    an infinite loop).
    """
    chain: list[Course] = []
    seen = {course.course_id}
    current = course
    while current.parent_course_id is not None:
        result = await db.execute(select(Course).where(Course.college_id == college_id, Course.course_id == current.parent_course_id))
        parent = result.scalars().first()
        if parent is None or parent.course_id in seen:
            break
        chain.append(parent)
        seen.add(parent.course_id)
        current = parent
    chain.reverse()
    return chain


async def programme_path(db, college_id: int, course: Course) -> str | None:
    """Breadcrumb for the summary-confirm prompt, e.g. "B.Tech" or "B.Tech > Engineering" for deeper nesting. None for a top-level course with no parent. Not underscore-prefixed - also used by the eligibility router to show staff a branch course's programme path."""
    ancestors = await _get_ancestor_chain(db, college_id, course)
    return " > ".join(a.course_name for a in ancestors) if ancestors else None


async def get_effective_rules(db, college_id: int, course: Course) -> list[EligibilityRule]:
    """
    Active rules that actually apply to `course`: every ancestor's active
    rules (root to nearest parent, in each level's own order) followed by
    the course's own active rules - a straight, always-additive merge, e.g.
    "PCM required, 75% aggregate" shared on a B.Tech parent plus a
    Computer-Science-only entrance cutoff on the branch itself. There's
    deliberately no override mechanism: a branch can only add rules on top
    of its ancestors', never replace one (see module docstring). Not
    underscore-prefixed since the eligibility router's course-preview
    endpoint also needs this, to show staff the inherited rules a branch
    would actually be checked against.
    """
    rules: list[EligibilityRule] = []
    for ancestor in await _get_ancestor_chain(db, college_id, course):
        result = await db.execute(select(EligibilityRule).where(EligibilityRule.college_id == college_id, EligibilityRule.course_id == ancestor.course_id, EligibilityRule.is_active == True).order_by(EligibilityRule.order_index))  # noqa: E712
        rules.extend(result.scalars().all())
    own_result = await db.execute(select(EligibilityRule).where(EligibilityRule.college_id == college_id, EligibilityRule.course_id == course.course_id, EligibilityRule.is_active == True).order_by(EligibilityRule.order_index))  # noqa: E712
    rules.extend(own_result.scalars().all())
    return rules


async def _get_course_with_rules(db, college_id: int, course_id: int) -> tuple[Course, list[EligibilityRule]] | tuple[None, None]:
    # Returns rules as a separate list rather than assigning into
    # course.eligibility_rules: that attribute is a real cascade="all,
    # delete-orphan" relationship, and since this only loads *active* rules
    # (and, for a branch course, rules from other rows entirely - see
    # _get_effective_rules), assigning a filtered list into it would make
    # SQLAlchemy think every inactive/foreign rule had been removed from the
    # collection - and delete them on the next commit.
    result = await db.execute(select(Course).where(Course.college_id == college_id, Course.course_id == course_id))
    course = result.scalars().first()
    if course is None:
        return None, None
    rules = await get_effective_rules(db, college_id, course)
    return course, rules


async def _get_all_leaf_courses(db, college_id: int) -> list[Course]:
    """
    Every published, individually eligibility-checkable course at a college
    - i.e. one with no published children of its own. A programme-type node
    ("B.Tech") is never itself a valid eligibility check or cross-sell
    suggestion even though it's a row in `courses` too, so it's excluded
    here. Used by _suggest_alternate_courses, which needs to search across
    the whole college rather than one list level at a time.
    """
    result = await db.execute(select(Course).where(Course.college_id == college_id, Course.is_published == True))  # noqa: E712
    all_courses = list(result.scalars().all())
    parent_ids_with_published_children = {c.parent_course_id for c in all_courses if c.parent_course_id is not None}
    return [c for c in all_courses if c.course_id not in parent_ids_with_published_children]


def _base_result(intro_text: str, interactive: dict | None, flow_state: dict | None, wants_human_handoff: bool = False, sources: list | None = None, input_tokens: int = 0, output_tokens: int = 0, model_used: str = "eligibility_flow") -> dict:
    """
    intro_text is any framing sentence on top of the question itself (e.g.
    "You don't meet the criteria for X."); the question/options are always
    rendered from `interactive` so the saved transcript matches what the
    student actually saw as buttons, instead of duplicating it by hand at
    every call site.

    Shape matches what whatsapp_chat.py already expects from agent.invoke(),
    plus `interactive` (how to actually send it) and `session_active_flow`
    (what to persist onto StudentSession.active_flow - None clears it).

    sources/input_tokens/output_tokens/model_used default to the flow's own
    "no LLM involved" values, but a step that borrows the RAG agent (see
    _handle_await_procedure_interest) passes its real ones through here
    instead, so citations and cost/model attribution downstream aren't
    silently overwritten with the eligibility-flow defaults.
    """
    if interactive:
        rendered = render_interactive_as_text(interactive)
        response_text = f"{intro_text}\n\n{rendered}" if intro_text else rendered
    else:
        response_text = intro_text
    if flow_state is not None:
        # Stamped centrally here (every flow-continuing return goes through
        # _base_result) rather than at each call site, so
        # FLOW_IDLE_TIMEOUT_MINUTES has one reliable source of truth to
        # measure against - see _is_flow_expired.
        flow_state = {**flow_state, "updated_at": datetime.now(timezone.utc).isoformat()}
    return {
        "response": response_text,
        "interactive": interactive,
        "updated_session_summary": None,
        "sources": sources or [],
        "model_used": model_used,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "wants_human_handoff": wants_human_handoff,
        "session_active_flow": flow_state,
    }


def _record_outcome(student, course_name: str, eligible: bool, failed_reason: str | None = None, borderline: bool = False) -> None:
    """
    Best-effort note for the dashboard/lead-scoring pipeline. Additive only -
    this must never clobber the other keys (concerns, guardian_involvement,
    etc.) that the LLM-driven student-profile pipeline owns in the same
    JSONB column.

    failed_reason (only set on eligible=False) records which specific
    requirement the student didn't meet, so staff looking at the profile
    later see more than a bare pass/fail. borderline marks a fail where the
    student said "close / not sure" rather than a confident No - see
    evaluate_rule_reply - so staff can tell a soft fail worth a second look
    apart from a clean one.
    """
    signals = dict(student.profile_signals or {})
    history = list(signals.get("eligibility_checks", []))
    entry = {"course": course_name, "eligible": eligible, "checked_at": datetime.now(timezone.utc).isoformat()}
    if failed_reason:
        entry["failed_reason"] = failed_reason
    if borderline:
        entry["borderline"] = True
    history.append(entry)
    signals["eligibility_checks"] = history[-10:]  # cap growth - this is a signal feed, not a full audit log
    student.profile_signals = signals


async def _record_eligibility_event(db, college_id: int, student_id: int, step: str, outcome: str, course_id: int | None = None, rule_index: int | None = None) -> None:
    """
    Append-only write to eligibility_events (see models/EligibilityEvent.py)
    for the admin analytics endpoint - pass/fail rate per course, and where
    students actually drop off. Deliberately separate from _record_outcome,
    which is a per-student *summary* (last 10 checks, folded into the
    LLM-driven profile_signals JSONB); this is a flat log built to be
    aggregated across every student in a college, and it's the only place
    a cancel/timeout gets recorded at all - _record_outcome never sees them.

    Best-effort: swallows and logs its own failures rather than raising, so
    a broken analytics write can never take down the actual student-facing
    flow it's instrumenting.
    """
    try:
        db.add(EligibilityEvent(college_id=college_id, student_id=student_id, course_id=course_id, step=step, rule_index=rule_index, outcome=outcome))
        await db.commit()
    except Exception:
        logger.warning("Failed to record eligibility_events row student_id=%s step=%s outcome=%s", student_id, step, outcome, exc_info=True)
        await db.rollback()


# --------------------------------------------------------------------------
# The state machine
# --------------------------------------------------------------------------

async def _render_step(db, college_id: int, flow_state: dict) -> dict:
    """
    Re-render the prompt for a given (already-visited) flow_state with no
    side effects - no db.commit, no _record_outcome. Used only by
    _handle_back to redisplay a step the student is returning to; every
    other call site builds its prompt inline as part of actually taking that
    step for the first time.
    """
    step = flow_state.get("step")
    if step == "await_start_confirm":
        return _base_result("", _start_confirm_prompt(), flow_state)
    if step == "await_course":
        parent_id = flow_state.get("parent_id")
        parent_name = flow_state.get("parent_name")
        courses = await _get_published_courses(db, college_id, parent_id)
        return _base_result("", _course_list_prompt(courses, parent_name), flow_state)
    if step == "await_category":
        return _base_result("", _category_prompt(), flow_state)
    if step == "await_summary_confirm":
        return _base_result("", _summary_prompt(flow_state.get("course_name", "this course"), flow_state.get("category"), flow_state.get("programme_path")), flow_state)
    if step == "await_rule":
        course_id = flow_state.get("course_id")
        rule_index = flow_state.get("rule_index", 0)
        category = flow_state.get("category")
        course, rules = await _get_course_with_rules(db, college_id, course_id)
        if course is None or rules is None or rule_index >= len(rules):
            return _base_result("That course isn't available anymore - let's start over.", None, None)
        return _base_result("", _with_rule_progress(build_rule_prompt(rules[rule_index], category), rule_index, len(rules)), flow_state)
    if step == "await_procedure_interest":
        return _base_result("", _procedure_interest_prompt(flow_state.get("course_name", "this course")), flow_state)
    if step == "await_another_course":
        return _base_result("", _another_course_prompt(), flow_state)
    logger.warning("Unrecognized step=%r while rendering a 'back' navigation", step)
    return _base_result("Sorry, something went wrong going back. Let's start over.", None, None)


async def _handle_back(db, college_id: int, flow: dict) -> dict:
    history = list(flow.get("history", []))
    if not history:
        # Already at the first correctable step - nothing earlier to show,
        # so just redisplay the current question with a short note rather
        # than silently ignoring the "back".
        current = {k: v for k, v in flow.items() if k != "history"}
        result = await _render_step(db, college_id, current)
        note = "You're at the first question of this check, so there's nothing before it."
        result["response"] = f"{note}\n\n{result['response']}" if result.get("response") else note
        if result.get("session_active_flow") is not None:
            result["session_active_flow"]["history"] = []
        return result

    prev, remaining_history = history[-1], history[:-1]
    result = await _render_step(db, college_id, {**prev, "history": remaining_history})
    note = "Sure, here's the previous question again:"
    result["response"] = f"{note}\n\n{result['response']}" if result.get("response") else note
    return result


async def handle_incoming_message(db, college_id: int, student, session, content: str, message_type: str, agent=None, request_id: str | None = None) -> dict:
    flow = (session.active_flow or {})
    step = flow.get("step")

    if step is not None and _is_flow_expired(flow):
        logger.info("Eligibility flow idle past %d min, resetting to free chat", FLOW_IDLE_TIMEOUT_MINUTES, extra={"extra_data": {"student_id": student.student_id, "stale_step": step}})
        await _record_eligibility_event(db, college_id, student.student_id, step, "timed_out", course_id=flow.get("course_id"), rule_index=flow.get("rule_index"))
        # Clear the flow rather than silently treating this message as an
        # answer to a question from (potentially) days ago. The student's
        # actual message - whatever it was about - just gets dropped this
        # one turn; if it's still relevant they can simply repeat it, and it
        # will now be routed to free chat / a fresh eligibility check
        # correctly instead of being misread as a stale button tap.
        return _base_result("Your last eligibility check timed out after being idle a while, so I've closed it out. Just say \"check eligibility\" any time to start again, or ask me anything else!", None, None)

    if _is_cancel(content, message_type):
        if step is not None:
            await _record_eligibility_event(db, college_id, student.student_id, step, "cancelled", course_id=flow.get("course_id"), rule_index=flow.get("rule_index"))
        return _base_result("No problem - exiting the eligibility check. Ask me anything else!", None, None)

    if step is not None and _is_back(content, message_type):
        return await _handle_back(db, college_id, flow)

    if step is None:
        confidence = _trigger_confidence(content, message_type)
        if confidence == "weak":
            # Don't assume - a weak match (typo, or a word like "qualify"/
            # "cutoff" that's often about something else) gets a cheap
            # one-tap confirmation instead of committing the student to the
            # full multi-question flow on a guess.
            return _start_confirmation_prompt()
        return await _start(db, college_id)

    if step == "await_start_confirm":
        return await _handle_await_start_confirm(db, college_id, content, message_type)

    if step == "await_course":
        return await _handle_await_course(db, college_id, student, flow, content, message_type)

    if step == "await_category":
        return await _handle_await_category(db, college_id, flow, content, message_type)

    if step == "await_summary_confirm":
        return await _handle_await_summary_confirm(db, college_id, flow, content, message_type)

    if step == "await_rule":
        return await _handle_await_rule(db, college_id, student, flow, content, message_type)

    if step == "await_procedure_interest":
        return await _handle_await_procedure_interest(db, college_id, student, session, flow, content, message_type, agent=agent, request_id=request_id)

    if step == "await_another_course":
        return await _handle_await_another_course(db, college_id, content, message_type)

    # Unrecognized/corrupt state - fail safe back to free chat rather than
    # getting a student stuck in a flow that can never resolve.
    logger.warning("Unknown eligibility flow step=%r for student_id=%s, resetting to free chat", step, student.student_id)
    return _base_result("Sorry, something went wrong with that. Let's start over - just ask your question.", None, None)


def _start_confirm_prompt() -> dict:
    return {
        "type": "button",
        "body": "Just to confirm - would you like to check your eligibility for one of our courses?",
        "buttons": [{"id": "confirm_start_yes", "title": "Yes, check"}, {"id": "confirm_start_no", "title": "No"}],
    }


def _start_confirmation_prompt() -> dict:
    flow_state = {"flow": FLOW_NAME, "step": "await_start_confirm"}
    return _base_result("", _start_confirm_prompt(), flow_state)


async def _handle_await_start_confirm(db, college_id: int, content: str, message_type: str) -> dict:
    confirms = (message_type == "interactive_button" and content == "confirm_start_yes") or (content or "").strip().lower() in ("yes", "y")
    declines = (message_type == "interactive_button" and content == "confirm_start_no") or (content or "").strip().lower() in ("no", "n")

    if confirms:
        return await _start(db, college_id)
    if declines:
        return _base_result("No worries! Feel free to ask me anything else.", None, None)
    return _base_result("Please tap Yes or No above.", _start_confirm_prompt(), {"flow": FLOW_NAME, "step": "await_start_confirm"})


async def _start(db, college_id: int) -> dict:
    courses = await _get_published_courses(db, college_id, None)
    if not courses:
        return _base_result("Eligibility checking isn't set up for this college yet - please contact the admissions office directly for now.", None, None)
    flow_state = {"flow": FLOW_NAME, "step": "await_course"}
    return _base_result("Sure, let's check your eligibility.", _course_list_prompt(courses), flow_state)


async def _handle_await_course(db, college_id: int, student, flow: dict, content: str, message_type: str) -> dict:
    parent_id = flow.get("parent_id")
    parent_name = flow.get("parent_name")
    courses = await _get_published_courses(db, college_id, parent_id)
    course = parse_course_reply(content, message_type, courses)
    if course is None:
        return _base_result("Sorry, I didn't catch that - please pick a course from the list, or type its name.", _course_list_prompt(courses, parent_name), flow)

    history = list(flow.get("history", [])) + [{"flow": FLOW_NAME, "step": "await_course", "parent_id": parent_id, "parent_name": parent_name}]

    if await _has_published_children(db, college_id, course.course_id):
        # This node is a programme type (e.g. "B.Tech"), not itself a
        # checkable course - drill one level deeper into its branches
        # instead of treating the tap as a final selection. This is what
        # keeps a college with 30+ courses out of one flat, 10-row-capped
        # WhatsApp list - see module docstring.
        flow_state = {"flow": FLOW_NAME, "step": "await_course", "parent_id": course.course_id, "parent_name": course.course_name, "history": history}
        children = await _get_published_courses(db, college_id, course.course_id)
        return _base_result("", _course_list_prompt(children, course.course_name), flow_state)

    student.course_interest = course.course_name
    _, rules = await _get_course_with_rules(db, college_id, course.course_id)
    programme_path_value = await programme_path(db, college_id, course)

    if not rules:
        await db.commit()
        return await _finish_eligible(db, college_id, student, course.course_id, course.course_name)

    if requires_category(rules):
        flow_state = {"flow": FLOW_NAME, "step": "await_category", "course_id": course.course_id, "programme_path": programme_path_value, "history": history}
        await db.commit()
        return _base_result(f"Checking eligibility for {course.course_name}.", _category_prompt(), flow_state)

    await db.commit()
    return _summary_confirm_result(course.course_id, course.course_name, category=None, history=history, programme_path=programme_path_value)


async def _handle_await_category(db, college_id: int, flow: dict, content: str, message_type: str) -> dict:
    course_id = flow["course_id"]
    programme_path = flow.get("programme_path")
    category = parse_category_reply(content, message_type)
    if category is None:
        return _base_result("Please select your category from the list.", _category_prompt(), flow)

    course, rules = await _get_course_with_rules(db, college_id, course_id)
    if course is None:
        return _base_result("That course isn't available anymore - let's start over.", None, None)
    history = list(flow.get("history", [])) + [{"flow": FLOW_NAME, "step": "await_category", "course_id": course_id, "programme_path": programme_path}]
    return _summary_confirm_result(course.course_id, course.course_name, category=category, history=history, programme_path=programme_path)


def _summary_confirm_result(course_id: int, course_name: str, category: str | None, history: list, programme_path: str | None = None) -> dict:
    flow_state = {"flow": FLOW_NAME, "step": "await_summary_confirm", "course_id": course_id, "course_name": course_name, "category": category, "programme_path": programme_path, "history": history}
    return _base_result("", _summary_prompt(course_name, category, programme_path), flow_state)


async def _handle_await_summary_confirm(db, college_id: int, flow: dict, content: str, message_type: str) -> dict:
    confirms = (message_type == "interactive_button" and content == "summary_confirm_yes") or (content or "").strip().lower() in ("yes", "y", "confirm", "go ahead", "proceed")
    if not confirms:
        return _base_result("Please tap \"Yes, check\" above, or type \"back\" to change something.", _summary_prompt(flow.get("course_name", "this course"), flow.get("category"), flow.get("programme_path")), flow)

    course_id = flow["course_id"]
    category = flow.get("category")
    course, rules = await _get_course_with_rules(db, college_id, course_id)
    if course is None or not rules:
        return _base_result("That course isn't available anymore - let's start over.", None, None)
    history = list(flow.get("history", [])) + [{"flow": FLOW_NAME, "step": "await_summary_confirm", "course_id": course_id, "course_name": course.course_name, "category": category, "programme_path": flow.get("programme_path")}]
    return _ask_rule(course.course_id, course.course_name, rules, rule_index=0, category=category, history=history)


def _ask_rule(course_id: int, course_name: str, rules: list[EligibilityRule], rule_index: int, category: str | None, history: list | None = None, known_stream: str | None = None) -> dict:
    rule = rules[rule_index]
    flow_state = {"flow": FLOW_NAME, "step": "await_rule", "course_id": course_id, "rule_index": rule_index, "category": category}
    if history is not None:
        flow_state["history"] = history
    if known_stream:
        flow_state["known_stream"] = known_stream
    prompt = build_rule_prompt(rule, category)
    prompt = _with_rule_progress(prompt, rule_index, len(rules))
    prefix = "" if rule_index > 0 else f"Checking eligibility for {course_name}."
    prompt = {**prompt, "body": (f"{prefix}\n\n{prompt['body']}" if prefix else prompt["body"])}
    return _base_result("", prompt, flow_state)


def _chosen_stream_label(rule: EligibilityRule, content: str, message_type: str) -> str | None:
    """
    evaluate_rule_reply only returns True/False for a required_stream rule,
    not which stream the student actually picked. Re-derive it (same
    matching evaluate_rule_reply itself uses) so a stream answered earlier
    in a course's rule list can be remembered in flow_state and reused for
    a cross-sell suggestion if a later rule in the same course fails - see
    _suggest_alternate_courses.
    """
    if rule.rule_type != "required_stream":
        return None
    c = rule.config
    if message_type == "interactive_list" and content.startswith("stream_"):
        slug = content[len("stream_"):]
        return next((s for s in c["allowed_streams"] if s.lower().replace(" ", "_") == slug), None)
    normalized = (content or "").strip().lower()
    return next((s for s in c["allowed_streams"] if s.lower() == normalized), None)


async def _suggest_alternate_courses(db, college_id: int, exclude_course_id: int, known_stream: str | None, limit: int = 3) -> list[Course]:
    """
    Best-effort cross-sell for the fail branch of _handle_await_rule: other
    published courses at this college, besides the one the student just
    failed, they might actually qualify for. Filtered to courses whose own
    required_stream rule (if any) accepts the student's already-known
    stream - see _chosen_stream_label for where that gets captured. Without
    a known stream this is just "other published courses you haven't asked
    about" rather than a guaranteed-eligible list, since without a captured
    stream there's nothing concrete left to filter on; we deliberately don't
    re-run every other rule (percentage/entrance cutoffs etc.) for every
    other course here - that needs the real numeric values this flow
    doesn't capture yet (see remaining-work item #3), not just a guess.
    """
    courses = await _get_all_leaf_courses(db, college_id)
    candidates = [c for c in courses if c.course_id != exclude_course_id]
    if not known_stream:
        return candidates[:limit]

    stream_key = known_stream.strip().lower()
    matches = []
    for c in candidates:
        _, rules = await _get_course_with_rules(db, college_id, c.course_id)
        stream_rule = next((r for r in (rules or []) if r.rule_type == "required_stream"), None)
        if stream_rule is None or stream_key in (s.strip().lower() for s in stream_rule.config.get("allowed_streams", [])):
            matches.append(c)
        if len(matches) >= limit:
            break
    return matches[:limit]


async def _handle_await_rule(db, college_id: int, student, flow: dict, content: str, message_type: str) -> dict:
    course_id = flow["course_id"]
    rule_index = flow["rule_index"]
    category = flow.get("category")
    known_stream = flow.get("known_stream")

    course, rules = await _get_course_with_rules(db, college_id, course_id)
    if course is None or rule_index >= len(rules):
        return _base_result("That course isn't available anymore - let's start over.", None, None)
    rule = rules[rule_index]

    passed = evaluate_rule_reply(rule, content, message_type)
    if passed is None:
        prompt = _with_rule_progress(build_rule_prompt(rule, category), rule_index, len(rules))
        return _base_result("Please tap one of the options above.", prompt, flow)

    if passed is True:
        known_stream = _chosen_stream_label(rule, content, message_type) or known_stream

    # Every fail/borderline/advance branch below pushes this rule's own step
    # onto history before leaving it, so "back" can return here even after a
    # rejection - a fat-fingered "No" doesn't have to mean restarting the
    # whole check (see the module docstring).
    history_with_this_rule = list(flow.get("history", [])) + [{"flow": FLOW_NAME, "step": "await_rule", "course_id": course_id, "rule_index": rule_index, "category": category}]

    if passed == "borderline":
        reason = describe_rule(rule, category)
        _record_outcome(student, course.course_name, eligible=False, failed_reason=reason, borderline=True)
        await _record_eligibility_event(db, college_id, student.student_id, "await_rule", "borderline", course_id=course_id, rule_index=rule_index)
        await db.commit()
        # A "close / not sure" answer is worth a human look rather than the
        # same flat rejection a confident No gets - same low-confidence-
        # queue mechanism as _finish_eligible's hot-lead flag, just for a
        # borderline fail instead of a clean pass.
        text = (
            f"Thanks for being upfront about that. Since you're not sure whether you meet this requirement for {course.course_name}:\n"
            f"• {reason}\n\n"
            "I've let our admissions team know so they can take a closer look, rather than giving you a flat no."
        )
        prompt = _another_course_prompt()
        flow_state = {"flow": FLOW_NAME, "step": "await_another_course", "history": history_with_this_rule}
        return _base_result(text, prompt, flow_state, wants_human_handoff=True)

    if not passed:
        reason = describe_rule(rule, category)
        _record_outcome(student, course.course_name, eligible=False, failed_reason=reason)
        await _record_eligibility_event(db, college_id, student.student_id, "await_rule", "failed", course_id=course_id, rule_index=rule_index)
        await db.commit()
        # Naming the specific unmet requirement (instead of a bare "you
        # don't meet the criteria") is more transparent and also lets a
        # student self-correct if they misread the question and try again -
        # and now they can also just type "back" and redo that one answer
        # instead of restarting, if it was a mis-tap rather than a real fail.
        text = (
            f"Based on that, you don't currently meet one of the eligibility requirements for {course.course_name}:\n"
            f"• {reason}\n\n"
            "If that doesn't sound right, type \"back\" to change that answer."
        )
        # Cross-sell: don't leave a rejected student with nothing but "try
        # another course?" when we may already know enough (their stream)
        # to point at something they'd likely actually qualify for.
        suggestions = await _suggest_alternate_courses(db, college_id, exclude_course_id=course_id, known_stream=known_stream)
        if suggestions:
            names = ", ".join(c.course_name for c in suggestions)
            stream_note = f" (open to {known_stream} stream)" if known_stream else ""
            text += f"\n\nYou might also want to look at{stream_note}: {names}."
        prompt = _another_course_prompt()
        flow_state = {"flow": FLOW_NAME, "step": "await_another_course", "history": history_with_this_rule}
        return _base_result(text, prompt, flow_state)

    next_index = rule_index + 1
    if next_index < len(rules):
        return _ask_rule(course_id, course.course_name, rules, rule_index=next_index, category=category, history=history_with_this_rule, known_stream=known_stream)

    await db.commit()
    return await _finish_eligible(db, college_id, student, course_id, course.course_name)


async def _finish_eligible(db, college_id: int, student, course_id: int, course_name: str) -> dict:
    _record_outcome(student, course_name, eligible=True)
    await _record_eligibility_event(db, college_id, student.student_id, "await_rule", "passed", course_id=course_id)
    await db.commit()
    prompt = _procedure_interest_prompt(course_name)
    flow_state = {"flow": FLOW_NAME, "step": "await_procedure_interest", "course_id": course_id, "course_name": course_name}
    # A student clearing every rule is the highest-intent moment in this
    # whole flow - piggyback on the same low-confidence-queue mechanism the
    # RAG agent already uses for human handoff so this "hot lead" shows up
    # for staff to follow up on right away, rather than only being visible
    # later as a buried entry in profile_signals.
    return _base_result("", prompt, flow_state, wants_human_handoff=True)


async def _ask_rag_about_procedure(agent, db, college_id: int, student, session, course_name: str, request_id: str | None) -> dict | None:
    """
    Best-effort lookup against the college's own RAG index (e.g. a
    brochure PDF - see rag/agent.py) for the admission procedure, so a
    confirmed-eligible student doesn't automatically hit a "not available"
    dead end when the college's own materials might already cover it.

    Returns the agent's result dict on a usable, *confident* answer, or
    None if the agent isn't wired up, the call errors, comes back empty, or
    comes back low-confidence (wants_human_handoff - the same flag the RAG
    graph sets when retrieval didn't turn up anything it trusted, or the
    model itself flagged uncertainty). Any of those fall back to the
    static "not available yet" reply rather than surfacing a shaky guess
    on something with real stakes for the student's application.
    """
    if agent is None:
        return None
    try:
        result = await agent.invoke(
            db,
            f"What is the admission procedure for {course_name}?",
            college_id=college_id,
            student_id=student.student_id,
            request_id=request_id or "eligibility_procedure",
            student_summary=student.summary,
            session_id=session.session_id,
            session_summary=session.session_summary,
        )
    except Exception:
        logger.warning("RAG lookup for admission procedure failed course_name=%r college_id=%s", course_name, college_id, exc_info=True)
        return None
    if result.get("error") is not None or not (result.get("response") or "").strip():
        return None
    if result.get("wants_human_handoff"):
        # Low-confidence retrieval or the model itself wasn't sure - don't
        # show a shaky answer, just fall back to the static reply below
        # (which still flags a human either way).
        return None
    return result


async def _handle_await_procedure_interest(db, college_id: int, student, session, flow: dict, content: str, message_type: str, agent=None, request_id: str | None = None) -> dict:
    wants_procedure = (message_type == "interactive_button" and content == "proc_yes") or (content or "").strip().lower() in ("yes", "y")
    declines = (message_type == "interactive_button" and content == "proc_no") or (content or "").strip().lower() in ("no", "n")

    if not wants_procedure and not declines:
        return _base_result("Please tap Yes or No above.", _procedure_interest_prompt(flow.get("course_name", "this course")), flow)

    prompt = _another_course_prompt()
    flow_state = {"flow": FLOW_NAME, "step": "await_another_course"}

    if wants_procedure:
        course_name = flow.get("course_name", "this course")
        rag_result = await _ask_rag_about_procedure(agent, db, college_id, student, session, course_name, request_id)

        if rag_result is not None:
            # A confirmed-eligible student asking about next steps is still
            # the highest-intent moment in this flow (same as
            # _finish_eligible) - notify staff regardless, since a
            # confident RAG answer here is a bonus for the student, not a
            # reason to skip the human follow-up.
            return _base_result(rag_result["response"], prompt, flow_state, wants_human_handoff=True, sources=rag_result.get("sources"), input_tokens=rag_result.get("input_tokens", 0), output_tokens=rag_result.get("output_tokens", 0), model_used=rag_result.get("model_used", "rag_fallback"))

        # No agent wired up, or RAG genuinely came up empty/errored - flag
        # for a human follow-up instead of guessing, same as before.
        text = "Thanks! The full admission procedure isn't available here yet, so I've let our admissions team know you're interested - they'll reach out with the details."
        return _base_result(text, prompt, flow_state, wants_human_handoff=True)

    return _base_result("", prompt, flow_state)


async def _handle_await_another_course(db, college_id: int, content: str, message_type: str) -> dict:
    wants_another = (message_type == "interactive_button" and content == "another_yes") or (content or "").strip().lower() in ("yes", "y")
    declines = (message_type == "interactive_button" and content == "another_no") or (content or "").strip().lower() in ("no", "n")

    if wants_another:
        return await _start(db, college_id)
    if declines:
        return _base_result("Glad I could help! Feel free to ask me anything else about admissions.", None, None)
    return _base_result("Please tap Yes or No above.", _another_course_prompt(), {"flow": FLOW_NAME, "step": "await_another_course"})
