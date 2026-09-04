import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Download, GraduationCap, Loader2, Search, ChevronRight } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useStudentList, exportStudents } from "@/hooks/useStudents"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { EmptyState, FilteredEmptyState } from "@/components/EmptyState"
import { leadScoreBand } from "@/lib/leadScore"
import { getSignalChips } from "@/lib/studentSignals"
import { timeSince } from "@/lib/formatTime"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"

const PAGE_SIZE = 15

export default function StudentsList() {
  const { college, hasNoCollege } = useCurrentCollege()
  const navigate = useNavigate()
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const debouncedSearch = useDebouncedValue(search, 350)
  const [isExporting, setIsExporting] = useState(false)

  // A new search term invalidates whatever page you were on - always land
  // back on page 1 rather than a now-meaningless "page 4 of a 1-page result".
  // Adjusting state directly during render (React's own recommended pattern
  // for this) rather than a useEffect - no extra render/flicker, and avoids
  // the setState-in-effect lint warning.
  const [prevSearch, setPrevSearch] = useState(debouncedSearch)
  if (debouncedSearch !== prevSearch) {
    setPrevSearch(debouncedSearch)
    setPage(1)
  }

  const { data, isLoading, isFetching, isError, error } = useStudentList(college?.college_id, {
    page,
    pageSize: PAGE_SIZE,
    search: debouncedSearch,
  })

  const students = data?.items || []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  async function handleExport() {
    setIsExporting(true)
    try {
      await exportStudents(college.college_id, debouncedSearch)
    } catch (err) {
      toast.error(err?.message || "Failed to export. Please try again.")
    } finally {
      setIsExporting(false)
    }
  }

  if (hasNoCollege) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="No college access yet"
        description="Your account isn't linked to a college yet. Contact an admin to get set up."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Students</h1>
          <p className="text-muted-foreground">Every student who's messaged {college.college_name}, sorted by lead score.</p>
        </div>
        {(total > 0 || debouncedSearch) && (
          <div className="flex gap-2">
            <div className="relative w-full sm:w-64">
              <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search name, phone, course..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
              />
            </div>
            <Button variant="outline" size="icon" onClick={handleExport} disabled={isExporting} title="Export to CSV">
              {isExporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
            </Button>
          </div>
        )}
      </div>

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load students. Please try again."}
        </p>
      )}

      {!isLoading && !isError && total === 0 && !debouncedSearch && (
        <EmptyState
          icon={GraduationCap}
          title="No students yet"
          description="Students will show up here once they message your WhatsApp number."
        />
      )}

      {!isLoading && total === 0 && debouncedSearch && (
        <FilteredEmptyState query={debouncedSearch} onClear={() => setSearch("")} itemLabel="students" />
      )}

      {(isLoading || students.length > 0) && (
        <Table className={isFetching && !isLoading ? "opacity-60 transition-opacity" : undefined}>
          <TableHeader>
            <TableRow>
              <TableHead>Student</TableHead>
              <TableHead>Signals</TableHead>
              <TableHead>Active</TableHead>
              <TableHead>Lead score</TableHead>
              <TableHead className="w-8"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={5} />
            ) : (
              students.map((student) => {
                const band = leadScoreBand(student.lead_score ?? 0)
                const score = student.lead_score ?? 0
                const chips = getSignalChips(student.profile_signals)
                const visibleChips = chips.slice(0, 2)
                const overflowChips = chips.slice(2)
                const lastActive = student.lead_score_updated_at || student.created_at
                return (
                  <TableRow
                    key={student.student_id}
                    className="group cursor-pointer"
                    onClick={(e) => {
                      // The name cell already has its own <Link> (for
                      // middle-click/ctrl-click "open in new tab" and for
                      // screen readers) - skip the extra navigate when the
                      // click originated on that link so it doesn't fire twice.
                      if (e.target.closest("a")) return
                      navigate(`/students/${student.student_id}`)
                    }}
                  >
                    <TableCell className="whitespace-normal">
                      <div className="flex items-start gap-3">
                        <div
                          className={`flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${band.avatarClassName}`}
                          aria-hidden="true"
                        >
                          {(student.student_name || "?").trim().charAt(0).toUpperCase() || "?"}
                        </div>
                        <div className="flex min-w-0 flex-col">
                          <Link to={`/students/${student.student_id}`} className="font-medium hover:underline">
                            {student.student_name || "Unnamed"}
                          </Link>
                          <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
                            <span>{student.student_phone}</span>
                            {student.course_interest && (
                              <>
                                <span aria-hidden="true">·</span>
                                <span className="truncate">{student.course_interest}</span>
                              </>
                            )}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      {chips.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {visibleChips.map((chip) => (
                            <Badge key={chip.key} variant="outline" title={chip.title} className={`gap-1 ${chip.className}`}>
                              <chip.icon className="size-3" />
                              {chip.label}
                            </Badge>
                          ))}
                          {overflowChips.length > 0 && (
                            <Badge
                              variant="outline"
                              className="text-muted-foreground"
                              title={overflowChips.map((c) => c.label).join(", ")}
                            >
                              +{overflowChips.length}
                            </Badge>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{lastActiveLabel(lastActive)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
                          <div
                            className={`h-full rounded-full ${band.barClassName}`}
                            style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
                          />
                        </div>
                        <Badge variant="outline" className={band.className}>
                          {score} · {band.label}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <ChevronRight className="size-4 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      )}

      {!isLoading && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}
    </div>
  )
}

// "3h ago" reads fine, but timeSince's own "just now" already implies
// recency without an "ago" - stacking them ("just now ago") doesn't.
function lastActiveLabel(iso) {
  if (!iso) return "—"
  const rel = timeSince(iso)
  return rel === "just now" ? rel : `${rel} ago`
}
