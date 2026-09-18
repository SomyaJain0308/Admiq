import { useState } from "react"
import { GraduationCap, Loader2, Plus, Trash2, ChevronUp, ChevronDown, Eye, X, BarChart3, AlertTriangle } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import {
  useCourses,
  useCourse,
  useCreateCourse,
  useUpdateCourse,
  useDeleteCourse,
  useCreateRule,
  useDeleteRule,
  useReorderRules,
  usePreviewCourse,
  useRuleConflicts,
  useEligibilityAnalytics,
} from "@/hooks/useEligibility"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Card } from "@/components/ui/card"
import { EmptyState } from "@/components/EmptyState"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"

// Plain-language labels for the rule templates staff pick from - kept in
// sync with backend/app/schemas/eligibility.py's RULE_CONFIG_MODELS.
const RULE_TYPES = [
  { value: "min_percentage", label: "Minimum overall percentage" },
  { value: "min_subject_marks", label: "Minimum marks in a subject" },
  { value: "required_stream", label: "Required stream" },
  { value: "entrance_cutoff", label: "Entrance exam cutoff" },
  { value: "category_cutoff", label: "Category-specific cutoff" },
  { value: "custom_yesno", label: "Custom yes/no requirement" },
]

const selectClass = "border-input flex h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"

// Plain-language labels for eligibility_events.step (see
// backend/app/models/EligibilityEvent.py) - used by the analytics panel's
// drop-off list.
const STEP_LABELS = {
  await_start_confirm: "Confirming they want to check eligibility",
  await_course: "Picking a course",
  await_category: "Picking their reservation category",
  await_summary_confirm: "Confirming course/category before rules run",
  await_rule: "Answering a rule question",
  await_procedure_interest: "Asked about the admission procedure",
  await_another_course: "Asked to check another course",
}

export default function EligibilityPage() {
  const { college, hasNoCollege } = useCurrentCollege()
  const collegeId = college?.college_id
  const { data: courses, isLoading, isError, error } = useCourses(collegeId)
  const createCourse = useCreateCourse(collegeId)
  const [newCourseName, setNewCourseName] = useState("")
  const [newCourseParentId, setNewCourseParentId] = useState("")
  const [selectedCourseId, setSelectedCourseId] = useState(null)
  const [confirmDeleteCourse, setConfirmDeleteCourse] = useState(null)
  const [showAnalytics, setShowAnalytics] = useState(false)
  const deleteCourse = useDeleteCourse(collegeId)

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Eligibility Checker</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  // Programme types staff can nest a new course under - only root-level
  // courses (no parent of their own), keeping the picker to the simple
  // "programme type -> branch" two-level shape even though the backend
  // itself supports deeper nesting. A college with more than 10 courses
  // creates a couple of these (e.g. "B.Tech", "BCA") first, then adds each
  // branch underneath one - see the note below the form.
  const rootCourses = (courses || []).filter((c) => !c.parent_course_id)

  async function handleAddCourse(e) {
    e.preventDefault()
    const name = newCourseName.trim()
    if (!name) return
    try {
      const course = await createCourse.mutateAsync({
        courseName: name,
        parentCourseId: newCourseParentId ? Number(newCourseParentId) : null,
      })
      setNewCourseName("")
      setNewCourseParentId("")
      setSelectedCourseId(course.course_id)
      toast.success(`${name} added.`)
    } catch (err) {
      toast.error(err?.message || "Failed to add course.")
    }
  }

  async function confirmDelete() {
    const course = confirmDeleteCourse
    if (!course) return
    setConfirmDeleteCourse(null)
    try {
      await deleteCourse.mutateAsync(course.course_id)
      if (selectedCourseId === course.course_id) setSelectedCourseId(null)
      toast.success(`${course.course_name} deleted.`)
    } catch (err) {
      toast.error(err?.message || "Failed to delete course.")
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Eligibility Checker</h1>
          <p className="text-muted-foreground">
            Configure courses and their eligibility rules - students check these on WhatsApp by asking to check their eligibility.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => setShowAnalytics((v) => !v)}>
          <BarChart3 className="size-4" />
          {showAnalytics ? "Hide analytics" : "Analytics"}
        </Button>
      </div>

      {showAnalytics && <EligibilityAnalyticsPanel collegeId={collegeId} />}

      <form onSubmit={handleAddCourse} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Input
            value={newCourseName}
            onChange={(e) => setNewCourseName(e.target.value)}
            placeholder="New course name, e.g. B.Tech CSE"
            className="max-w-sm"
          />
          <select className={`${selectClass} max-w-xs`} value={newCourseParentId} onChange={(e) => setNewCourseParentId(e.target.value)}>
            <option value="">No parent programme (top-level)</option>
            {rootCourses.map((c) => (
              <option key={c.course_id} value={c.course_id}>Under: {c.course_name}</option>
            ))}
          </select>
          <Button type="submit" disabled={!newCourseName.trim() || createCourse.isPending}>
            {createCourse.isPending ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
            Add course
          </Button>
        </div>
        {rootCourses.length > 0 && (
          <p className="text-xs text-muted-foreground">
            More than 10 courses at a college? Create a grouping course first (e.g. "B.Tech"), then add each branch (e.g. "Computer Science") under it - students will pick the group, then the branch, instead of hitting WhatsApp's 10-item list limit.
          </p>
        )}
      </form>

      {isError && <p role="alert" className="text-sm text-destructive">{error?.message || "Failed to load courses."}</p>}

      {!isLoading && !isError && courses?.length === 0 && (
        <EmptyState
          icon={GraduationCap}
          title="No courses yet"
          description="Add a course above, then configure the eligibility rules students will be checked against on WhatsApp."
        />
      )}

      {!isLoading && courses?.length > 0 && (
        <div className="grid gap-4 md:grid-cols-[280px_1fr]">
          <CourseTree courses={courses} selectedCourseId={selectedCourseId} onSelect={setSelectedCourseId} />

          {selectedCourseId ? (
            <CourseEditor
              collegeId={collegeId}
              courseId={selectedCourseId}
              rootCourses={rootCourses}
              onDeleteCourse={(course) => setConfirmDeleteCourse(course)}
            />
          ) : (
            <div className="flex items-center justify-center rounded-xl border border-dashed py-16 text-sm text-muted-foreground">
              Select a course to configure its eligibility rules.
            </div>
          )}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmDeleteCourse}
        onOpenChange={(open) => !open && setConfirmDeleteCourse(null)}
        title={`Delete "${confirmDeleteCourse?.course_name}"?`}
        description={
          confirmDeleteCourse && courses?.some((c) => c.parent_course_id === confirmDeleteCourse.course_id)
            ? "This is a parent programme with branches under it - they'll move back to the top level rather than being deleted, but every rule on this course itself will be removed. This can't be undone."
            : "Every rule for this course will be removed too, and students will no longer see it in the eligibility checker. This can't be undone."
        }
        onConfirm={confirmDelete}
        isConfirming={deleteCourse.isPending}
      />
    </div>
  )
}

function EligibilityAnalyticsPanel({ collegeId }) {
  const { data, isLoading, isError, error } = useEligibilityAnalytics(collegeId)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center rounded-xl border py-12">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isError) {
    return <p role="alert" className="text-sm text-destructive">{error?.message || "Failed to load analytics."}</p>
  }

  const courseStats = data?.course_stats || []
  const dropOffPoints = data?.drop_off_points || []

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="flex flex-col gap-3 p-4">
        <h3 className="text-sm font-semibold">Pass rate by course</h3>
        {courseStats.length === 0 ? (
          <p className="text-sm text-muted-foreground">No completed eligibility checks yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {courseStats.map((c) => (
              <div key={c.course_id} className="flex flex-col gap-1 rounded-md bg-muted/40 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{c.course_name}</span>
                  <span className="text-sm font-semibold">{Math.round(c.pass_rate * 100)}%</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {c.passed} passed - {c.failed} failed - {c.borderline} borderline ({c.total_completed} total)
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="flex flex-col gap-3 p-4">
        <h3 className="text-sm font-semibold">Where students drop off</h3>
        {dropOffPoints.length === 0 ? (
          <p className="text-sm text-muted-foreground">No cancellations or timeouts recorded yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {dropOffPoints.map((d, i) => (
              <div key={i} className="flex flex-col gap-1 rounded-md bg-muted/40 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{d.course_name || "Before picking a course"}</span>
                  <span className="text-sm font-semibold">{d.drop_offs}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {STEP_LABELS[d.step] || d.step}
                  {d.rule_description ? ` - "${d.rule_description}"` : ""}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

// Renders the flat `courses` list (each carrying parent_course_id) as a
// two-level tree: top-level courses/programme types, with any branches
// indented directly beneath their parent. Grouping happens client-side
// since the API returns courses flat - it's simpler for staff to scan a
// flat page than to build real tree UI for what's meant to stay a shallow
// hierarchy.
function CourseTree({ courses, selectedCourseId, onSelect }) {
  const byParent = {}
  for (const c of courses) {
    const key = c.parent_course_id || "root"
    if (!byParent[key]) byParent[key] = []
    byParent[key].push(c)
  }
  const roots = byParent.root || []

  function renderRow(c, depth) {
    const children = byParent[c.course_id] || []
    return (
      <div key={c.course_id} className="flex flex-col gap-2">
        <button
          type="button"
          onClick={() => onSelect(c.course_id)}
          style={{ marginLeft: depth * 16 }}
          className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
            selectedCourseId === c.course_id ? "border-primary bg-primary/5" : "hover:bg-muted/50"
          }`}
        >
          <div className="flex flex-col">
            <span className="font-medium">{c.course_name}</span>
            <span className="text-xs text-muted-foreground">
              {children.length > 0 ? `Programme type - ${children.length} branch${children.length === 1 ? "" : "es"}` : `${c.rule_count} rule${c.rule_count === 1 ? "" : "s"}`}
            </span>
          </div>
          <Badge variant={c.is_published ? "secondary" : "outline"}>{c.is_published ? "Published" : "Draft"}</Badge>
        </button>
        {children.map((child) => renderRow(child, depth + 1))}
      </div>
    )
  }

  return <div className="flex flex-col gap-2">{roots.map((c) => renderRow(c, 0))}</div>
}

function CourseEditor({ collegeId, courseId, rootCourses, onDeleteCourse }) {
  const { data: course, isLoading } = useCourse(collegeId, courseId)
  const updateCourse = useUpdateCourse(collegeId, courseId)
  const deleteRule = useDeleteRule(collegeId, courseId)
  const reorderRules = useReorderRules(collegeId, courseId)
  const { data: conflictData } = useRuleConflicts(collegeId, courseId, true)
  const [showAddRule, setShowAddRule] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [confirmDeleteRule, setConfirmDeleteRule] = useState(null)

  if (isLoading || !course) {
    return (
      <div className="flex items-center justify-center rounded-xl border py-16">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  async function togglePublished() {
    try {
      await updateCourse.mutateAsync({ is_published: !course.is_published })
      toast.success(course.is_published ? "Course unpublished - hidden from students for now." : "Course published - students can now select it.")
    } catch (err) {
      toast.error(err?.message || "Failed to update course.")
    }
  }

  async function changeParent(e) {
    const value = e.target.value
    try {
      await updateCourse.mutateAsync({ parent_course_id: value ? Number(value) : null })
      toast.success(value ? "Moved under the selected programme." : "Moved back to the top level.")
    } catch (err) {
      toast.error(err?.message || "Failed to move course.")
    }
  }

  async function moveRule(index, direction) {
    const ids = course.rules.map((r) => r.rule_id)
    const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    try {
      await reorderRules.mutateAsync(ids)
    } catch (err) {
      toast.error(err?.message || "Failed to reorder rules.")
    }
  }

  async function confirmDelete() {
    const rule = confirmDeleteRule
    if (!rule) return
    setConfirmDeleteRule(null)
    try {
      await deleteRule.mutateAsync(rule.rule_id)
      toast.success("Rule deleted.")
    } catch (err) {
      toast.error(err?.message || "Failed to delete rule.")
    }
  }

  // Candidate parents exclude this course itself (a course can't be its
  // own parent) - the backend rejects that and any deeper cycle too, this
  // is just keeping obviously-invalid options off the list.
  const parentOptions = (rootCourses || []).filter((c) => c.course_id !== course.course_id)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          {course.programme_path && <p className="text-xs font-medium text-muted-foreground">{course.programme_path}</p>}
          <h2 className="text-lg font-semibold">{course.course_name}</h2>
          <p className="text-sm text-muted-foreground">
            Rules are checked in order, top to bottom - the flow stops (and tells the student they're not eligible) at the first "No".
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setShowPreview(true)}>
            <Eye className="size-4" />
            Preview
          </Button>
          <Button type="button" variant={course.is_published ? "outline" : "default"} size="sm" onClick={togglePublished} disabled={updateCourse.isPending}>
            {course.is_published ? "Unpublish" : "Publish"}
          </Button>
          <Button type="button" variant="ghost" size="icon" aria-label="Delete course" onClick={() => onDeleteCourse(course)}>
            <Trash2 className="size-4 text-muted-foreground" />
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 max-w-xs">
        <Label className="text-xs text-muted-foreground">Parent programme</Label>
        <select className={selectClass} value={course.parent_course_id || ""} onChange={changeParent} disabled={updateCourse.isPending}>
          <option value="">No parent (top-level)</option>
          {parentOptions.map((c) => (
            <option key={c.course_id} value={c.course_id}>{c.course_name}</option>
          ))}
        </select>
      </div>

      {!course.is_published && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          This course is a draft - it won't show up in the WhatsApp eligibility checker until you publish it.
        </p>
      )}

      {conflictData?.conflicts?.length > 0 && (
        <div className="flex flex-col gap-2">
          {conflictData.conflicts.map((c, i) => (
            <p
              key={i}
              className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${
                c.severity === "error"
                  ? "border-destructive/30 bg-destructive/10 text-destructive"
                  : "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
              }`}
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {c.message}
            </p>
          ))}
        </div>
      )}

      {course.inherited_rules?.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground">Inherited from {course.programme_path} - asked before this course's own rules, edit them on that course instead</p>
          {course.inherited_rules.map((rule) => (
            <Card key={rule.rule_id} className="flex flex-row items-center gap-3 border-dashed p-3 opacity-80">
              <div>
                <p className="text-sm font-medium">{rule.generated_question}</p>
                <p className="text-xs text-muted-foreground">{RULE_TYPES.find((t) => t.value === rule.rule_type)?.label}</p>
              </div>
            </Card>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        {course.rules.length === 0 && (
          <p className="rounded-lg border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
            No rules yet - a course with no rules (and no inherited ones) is treated as always eligible.
          </p>
        )}
        {course.rules.map((rule, index) => (
          <Card key={rule.rule_id} className="flex flex-row items-center justify-between gap-3 p-3">
            <div className="flex items-center gap-2">
              <div className="flex flex-col">
                <Button type="button" variant="ghost" size="icon" className="size-5" disabled={index === 0} onClick={() => moveRule(index, -1)} aria-label="Move up">
                  <ChevronUp className="size-3.5" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="size-5" disabled={index === course.rules.length - 1} onClick={() => moveRule(index, 1)} aria-label="Move down">
                  <ChevronDown className="size-3.5" />
                </Button>
              </div>
              <div>
                <p className="text-sm font-medium">{rule.generated_question}</p>
                <p className="text-xs text-muted-foreground">{RULE_TYPES.find((t) => t.value === rule.rule_type)?.label}</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {!rule.is_active && <Badge variant="outline">Inactive</Badge>}
              <Button type="button" variant="ghost" size="icon" aria-label="Delete rule" onClick={() => setConfirmDeleteRule(rule)}>
                <Trash2 className="size-4 text-muted-foreground" />
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => setShowAddRule(true)}>
        <Plus className="size-4" />
        Add eligibility rule
      </Button>

      {showAddRule && <AddRuleDialog collegeId={collegeId} courseId={courseId} onClose={() => setShowAddRule(false)} />}
      {showPreview && <PreviewDialog collegeId={collegeId} courseId={courseId} onClose={() => setShowPreview(false)} />}

      <ConfirmDialog
        open={!!confirmDeleteRule}
        onOpenChange={(open) => !open && setConfirmDeleteRule(null)}
        title="Delete this rule?"
        description="Students checking eligibility for this course will no longer be asked about it."
        onConfirm={confirmDelete}
        isConfirming={deleteRule.isPending}
      />
    </div>
  )
}

function PreviewDialog({ collegeId, courseId, onClose }) {
  const { data, isLoading } = usePreviewCourse(collegeId, courseId, true)
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>What the student will be asked</DialogTitle>
          <DialogDescription>A plain-English walkthrough of the flow, in order.</DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <ol className="flex flex-col gap-2 text-sm">
            {data?.steps.map((step, i) => (
              <li key={i} className="rounded-md bg-muted/40 px-3 py-2">{step}</li>
            ))}
          </ol>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// One sub-form per rule template - each collects exactly the config fields
// its rule_type needs (see backend/app/schemas/eligibility.py).
function AddRuleDialog({ collegeId, courseId, onClose }) {
  const [ruleType, setRuleType] = useState("min_percentage")
  const createRule = useCreateRule(collegeId, courseId)

  const [label, setLabel] = useState("12th percentage")
  const [minValue, setMinValue] = useState("")
  const [subject, setSubject] = useState("")
  const [streams, setStreams] = useState(["Science (PCM)"])
  const [examName, setExamName] = useState("")
  const [metric, setMetric] = useState("percentile")
  const [threshold, setThreshold] = useState("")
  const [metricLabel, setMetricLabel] = useState("12th percentage")
  const [categoryThresholds, setCategoryThresholds] = useState({ general: "", obc: "", sc: "", st: "", ews: "" })
  const [customQuestion, setCustomQuestion] = useState("")
  const [passAnswer, setPassAnswer] = useState("yes")

  function buildConfig() {
    if (ruleType === "min_percentage") return { label, min_value: Number(minValue) }
    if (ruleType === "min_subject_marks") return { subject, min_value: Number(minValue) }
    if (ruleType === "required_stream") return { allowed_streams: streams.filter(Boolean) }
    if (ruleType === "entrance_cutoff") return { exam_name: examName, metric, threshold: Number(threshold) }
    if (ruleType === "category_cutoff") {
      const thresholds = {}
      for (const [k, v] of Object.entries(categoryThresholds)) {
        if (v !== "") thresholds[k] = Number(v)
      }
      return { metric_label: metricLabel, thresholds, higher_is_better: true }
    }
    if (ruleType === "custom_yesno") return { question: customQuestion, pass_answer: passAnswer }
    return {}
  }

  function isValid() {
    if (ruleType === "min_percentage") return label.trim() && minValue !== ""
    if (ruleType === "min_subject_marks") return subject.trim() && minValue !== ""
    if (ruleType === "required_stream") return streams.filter(Boolean).length > 0
    if (ruleType === "entrance_cutoff") return examName.trim() && threshold !== ""
    if (ruleType === "category_cutoff") return metricLabel.trim() && Object.values(categoryThresholds).some((v) => v !== "")
    if (ruleType === "custom_yesno") return customQuestion.trim()
    return false
  }

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await createRule.mutateAsync({ ruleType, config: buildConfig() })
      toast.success("Rule added.")
      onClose()
    } catch (err) {
      toast.error(err?.message || "Failed to add rule - check the values you entered.")
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add eligibility rule</DialogTitle>
          <DialogDescription>Pick the kind of requirement, then fill in its details. Students see this as a single tap-to-answer question.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Rule type</Label>
            <select className={selectClass} value={ruleType} onChange={(e) => setRuleType(e.target.value)}>
              {RULE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {ruleType === "min_percentage" && (
            <>
              <Field label="What is this a percentage of?">
                <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="12th percentage" />
              </Field>
              <Field label="Minimum value (%)">
                <Input type="number" min="0" max="100" value={minValue} onChange={(e) => setMinValue(e.target.value)} placeholder="60" />
              </Field>
            </>
          )}

          {ruleType === "min_subject_marks" && (
            <>
              <Field label="Subject">
                <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Maths" />
              </Field>
              <Field label="Minimum marks (%)">
                <Input type="number" min="0" max="100" value={minValue} onChange={(e) => setMinValue(e.target.value)} placeholder="60" />
              </Field>
            </>
          )}

          {ruleType === "required_stream" && (
            <Field label="Allowed streams">
              <StreamListEditor streams={streams} setStreams={setStreams} />
            </Field>
          )}

          {ruleType === "entrance_cutoff" && (
            <>
              <Field label="Exam name">
                <Input value={examName} onChange={(e) => setExamName(e.target.value)} placeholder="JEE Main" />
              </Field>
              <Field label="Measured as">
                <select className={selectClass} value={metric} onChange={(e) => setMetric(e.target.value)}>
                  <option value="percentile">Percentile (higher is better)</option>
                  <option value="rank">Rank (lower is better)</option>
                </select>
              </Field>
              <Field label="Threshold">
                <Input type="number" value={threshold} onChange={(e) => setThreshold(e.target.value)} placeholder={metric === "rank" ? "50000" : "90"} />
              </Field>
            </>
          )}

          {ruleType === "category_cutoff" && (
            <>
              <Field label="What does the cutoff measure?">
                <Input value={metricLabel} onChange={(e) => setMetricLabel(e.target.value)} placeholder="12th percentage" />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                {Object.keys(categoryThresholds).map((key) => (
                  <Field key={key} label={key.toUpperCase()}>
                    <Input
                      type="number"
                      value={categoryThresholds[key]}
                      onChange={(e) => setCategoryThresholds((prev) => ({ ...prev, [key]: e.target.value }))}
                      placeholder="e.g. 60"
                    />
                  </Field>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">Leave a category blank if it doesn't apply - a student who picks it falls back to the lowest configured threshold.</p>
            </>
          )}

          {ruleType === "custom_yesno" && (
            <>
              <Field label="Question to ask the student">
                <Textarea value={customQuestion} onChange={(e) => setCustomQuestion(e.target.value)} placeholder="Have you cleared all Class 12 subjects with no backlog?" />
              </Field>
              <Field label="Which answer passes?">
                <select className={selectClass} value={passAnswer} onChange={(e) => setPassAnswer(e.target.value)}>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </Field>
            </>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={!isValid() || createRule.isPending}>
              {createRule.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
              Add rule
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

function StreamListEditor({ streams, setStreams }) {
  function update(i, value) {
    setStreams((prev) => prev.map((s, idx) => (idx === i ? value : s)))
  }
  function remove(i) {
    setStreams((prev) => prev.filter((_, idx) => idx !== i))
  }
  return (
    <div className="flex flex-col gap-2">
      {streams.map((s, i) => (
        <div key={i} className="flex gap-2">
          <Input value={s} onChange={(e) => update(i, e.target.value)} placeholder="Science (PCM)" />
          <Button type="button" variant="ghost" size="icon" onClick={() => remove(i)} aria-label="Remove stream">
            <X className="size-4" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => setStreams((prev) => [...prev, ""])}>
        <Plus className="size-4" />
        Add stream
      </Button>
    </div>
  )
}
