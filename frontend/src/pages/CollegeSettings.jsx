import { useEffect, useRef, useState } from "react"
import { Loader2, Plus, Trash2, ArrowUp, ArrowDown, Sparkles, Undo2 } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useCollegeDetail, useUpdateCollege } from "@/hooks/useCollege"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
import { cn } from "@/lib/utils"

const MAX_STRENGTHS = 10
const MAX_STRENGTH_LENGTH = 120

// Light-touch starter ideas shown only when the list is empty, so staff
// aren't staring at a blank card. Clicking one just adds it as a normal,
// editable row - it's a starting point, not a fixed option.
const SUGGESTED_STRENGTHS = [
  "Strong placement record",
  "Affordable fees vs similar colleges",
  "On-campus hostel with 24/7 security",
  "Scholarships for eligible students",
  "Close to major hiring hubs",
]

let idCounter = 0
function makeRowId() {
  idCounter += 1
  return `strength-${idCounter}`
}

function toRows(strengths) {
  return (strengths || []).map((value) => ({ id: makeRowId(), value }))
}

function normalizeStrengths(rows) {
  return rows.map((r) => r.value.trim()).filter(Boolean)
}

// Rows whose trimmed, case-insensitive text collides with another row.
// Blank rows never count as duplicates of each other.
function findDuplicateIds(rows) {
  const seen = new Map()
  const dupes = new Set()
  for (const r of rows) {
    const v = r.value.trim().toLowerCase()
    if (!v) continue
    if (seen.has(v)) {
      dupes.add(r.id)
      dupes.add(seen.get(v))
    } else {
      seen.set(v, r.id)
    }
  }
  return dupes
}

export default function CollegeSettings() {
  const { college: currentCollege, hasNoCollege } = useCurrentCollege()
  const { data: college, isLoading } = useCollegeDetail(currentCollege?.college_id)
  const updateMutation = useUpdateCollege(currentCollege?.college_id)

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">College settings</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  if (isLoading || !college) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading college settings...
      </div>
    )
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">College settings</h1>
        <p className="text-muted-foreground">Basic info and admissions assistant configuration.</p>
      </div>

      {/* key={college.college_id} makes React remount this form (and re-run
          its useState initializer) whenever the selected college changes,
          instead of needing a useEffect to sync form state to fetched data -
          this is React's own recommended pattern for "reset state when a
          prop changes" rather than calling setState from inside an effect. */}
      <CollegeSettingsForm key={college.college_id} college={college} updateMutation={updateMutation} />
    </div>
  )
}

function CollegeSettingsForm({ college, updateMutation }) {
  const [form, setForm] = useState(() => ({
    college_name: college.college_name,
    college_phone: college.college_phone,
    college_email: college.college_email,
  }))
  const [rows, setRows] = useState(() => toRows(college.college_strengths))
  const [pendingFocusId, setPendingFocusId] = useState(null)
  const inputRefs = useRef({})

  // Stable snapshot of what's actually saved server-side, so we can tell
  // whether there are unsaved changes and offer a "discard" that reverts
  // to it - never changes except right after a successful save.
  const savedSnapshot = useRef({
    ...form,
    strengths: college.college_strengths || [],
  })

  const currentStrengths = normalizeStrengths(rows)
  const duplicateIds = findDuplicateIds(rows)
  const hasOverLengthRow = rows.some((r) => r.value.length > MAX_STRENGTH_LENGTH)
  const hasBlockingErrors = duplicateIds.size > 0 || hasOverLengthRow
  const atMaxStrengths = rows.length >= MAX_STRENGTHS

  const isDirty =
    form.college_name !== savedSnapshot.current.college_name ||
    form.college_phone !== savedSnapshot.current.college_phone ||
    form.college_email !== savedSnapshot.current.college_email ||
    JSON.stringify(currentStrengths) !== JSON.stringify(savedSnapshot.current.strengths)

  // Warn before an accidental tab-close/navigation with unsaved edits -
  // otherwise there's no signal at all that work is about to be lost.
  useEffect(() => {
    if (!isDirty) return
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [isDirty])

  useEffect(() => {
    if (!pendingFocusId) return
    inputRefs.current[pendingFocusId]?.focus()
    setPendingFocusId(null)
  }, [pendingFocusId])

  function updateRowValue(id, value) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, value } : r)))
  }

  function trimRowOnBlur(id) {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, value: r.value.trim() } : r)))
  }

  function addRowAfter(index) {
    if (rows.length >= MAX_STRENGTHS) {
      toast.warning(`You can list up to ${MAX_STRENGTHS} strengths - trim the list before adding more.`)
      return
    }
    const id = makeRowId()
    setRows((prev) => {
      const next = [...prev]
      next.splice(index + 1, 0, { id, value: "" })
      return next
    })
    setPendingFocusId(id)
  }

  function removeRow(id) {
    setRows((prev) => prev.filter((r) => r.id !== id))
  }

  function moveRow(index, direction) {
    setRows((prev) => {
      const target = index + direction
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  function addSuggestion(text) {
    if (rows.length >= MAX_STRENGTHS) return
    const id = makeRowId()
    setRows((prev) => [...prev, { id, value: text }])
  }

  function handleDiscard() {
    setForm({
      college_name: savedSnapshot.current.college_name,
      college_phone: savedSnapshot.current.college_phone,
      college_email: savedSnapshot.current.college_email,
    })
    setRows(toRows(savedSnapshot.current.strengths))
    toast.info("Changes discarded.")
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (hasBlockingErrors) {
      toast.error("Fix the highlighted strengths before saving.")
      return
    }

    try {
      await updateMutation.mutateAsync({
        college_name: form.college_name,
        college_phone: form.college_phone,
        college_email: form.college_email,
        college_strengths: currentStrengths,
      })
      // Drop any blank rows left over from editing and reset ids so the
      // list matches exactly what got saved.
      setRows(toRows(currentStrengths))
      savedSnapshot.current = { ...form, strengths: currentStrengths }
      toast.success("College settings saved.")
    } catch (err) {
      toast.error(err?.message || "Failed to save changes. Please try again.")
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Contact info</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="college_name">College name</Label>
            <Input
              id="college_name"
              required
              minLength={2}
              value={form.college_name}
              onChange={(e) => setForm((f) => ({ ...f, college_name: e.target.value }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="college_phone">Phone</Label>
              <Input
                id="college_phone"
                required
                minLength={10}
                value={form.college_phone}
                onChange={(e) => setForm((f) => ({ ...f, college_phone: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="college_email">Email</Label>
              <Input
                id="college_email"
                type="email"
                required
                value={form.college_email}
                onChange={(e) => setForm((f) => ({ ...f, college_email: e.target.value }))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Key strengths</CardTitle>
          <CardDescription>
            Up to {MAX_STRENGTHS}, listed in priority order - the assistant leans on these first when writing
            personalized check-in messages to students who've gone quiet. Keep each one short and specific (under{" "}
            {MAX_STRENGTH_LENGTH} characters) so it reads naturally in a chat message.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {rows.length === 0 ? (
            <div className="flex flex-col items-start gap-3 rounded-md border border-dashed p-4">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Sparkles className="size-4" />
                No strengths added yet. The assistant won't have anything to highlight in re-engagement messages.
              </div>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_STRENGTHS.map((text) => (
                  <Badge
                    key={text}
                    asChild
                    variant="outline"
                    className="cursor-pointer hover:bg-accent"
                  >
                    <button type="button" onClick={() => addSuggestion(text)}>
                      <Plus className="size-3" />
                      {text}
                    </button>
                  </Badge>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {rows.map((row, index) => {
                const isDuplicate = duplicateIds.has(row.id)
                const isOverLength = row.value.length > MAX_STRENGTH_LENGTH
                const isNearLimit = !isOverLength && row.value.length >= MAX_STRENGTH_LENGTH - 15
                return (
                  <div key={row.id} className="flex flex-col gap-1">
                    <div className="flex items-center gap-1">
                      <div className="flex flex-col">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="size-6"
                          disabled={index === 0}
                          onClick={() => moveRow(index, -1)}
                          aria-label="Move up"
                        >
                          <ArrowUp className="size-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="size-6"
                          disabled={index === rows.length - 1}
                          onClick={() => moveRow(index, 1)}
                          aria-label="Move down"
                        >
                          <ArrowDown className="size-3.5" />
                        </Button>
                      </div>
                      <Input
                        ref={(el) => {
                          if (el) inputRefs.current[row.id] = el
                          else delete inputRefs.current[row.id]
                        }}
                        value={row.value}
                        aria-invalid={isDuplicate || isOverLength}
                        placeholder="e.g. 95% placement rate over the last 3 years"
                        onChange={(e) => updateRowValue(row.id, e.target.value)}
                        onBlur={() => trimRowOnBlur(row.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault()
                            addRowAfter(index)
                          }
                        }}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeRow(row.id)}
                        aria-label="Remove strength"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                    {(isDuplicate || isOverLength || isNearLimit) && (
                      <div className="flex justify-between pl-14 text-xs">
                        <span className={cn(isDuplicate || isOverLength ? "text-destructive" : "invisible")}>
                          {isDuplicate ? "This strength is listed more than once." : isOverLength ? "Too long - try to trim this down." : ""}
                        </span>
                        <span className={cn(isOverLength ? "text-destructive" : "text-muted-foreground")}>
                          {row.value.length}/{MAX_STRENGTH_LENGTH}
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={atMaxStrengths}
              onClick={() => addRowAfter(rows.length - 1)}
            >
              <Plus className="size-3.5" />
              Add strength
            </Button>
            <span className="text-xs text-muted-foreground">
              {rows.length}/{MAX_STRENGTHS}
            </span>
          </div>
        </CardContent>
        <CardFooter className="flex items-center gap-3">
          <Button type="submit" disabled={updateMutation.isPending || !isDirty || hasBlockingErrors}>
            {updateMutation.isPending ? "Saving..." : "Save changes"}
          </Button>
          {isDirty && !updateMutation.isPending && (
            <>
              <span className="text-xs text-muted-foreground">Unsaved changes</span>
              <Button type="button" variant="ghost" size="sm" onClick={handleDiscard}>
                <Undo2 className="size-3.5" />
                Discard
              </Button>
            </>
          )}
        </CardFooter>
      </Card>
    </form>
  )
}
