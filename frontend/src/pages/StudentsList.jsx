import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Download, GraduationCap, Loader2, Search, TriangleAlert } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useStudentList, exportStudents } from "@/hooks/useStudents"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { leadScoreBand } from "@/lib/leadScore"
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
        <EmptyState title="No students yet" description="Students will show up here once they message your WhatsApp number." />
      )}

      {!isLoading && total === 0 && debouncedSearch && (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
          No students match "{debouncedSearch}".
          <Button variant="link" size="sm" className="h-auto p-0 text-sm" onClick={() => setSearch("")}>
            Clear search
          </Button>
        </p>
      )}

      {(isLoading || students.length > 0) && (
        <Table className={isFetching && !isLoading ? "opacity-60 transition-opacity" : undefined}>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Course interest</TableHead>
              <TableHead>Signals</TableHead>
              <TableHead>Lead score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={5} />
            ) : (
              students.map((student) => {
                const band = leadScoreBand(student.lead_score ?? 0)
                const concernCount = student.profile_signals?.concerns?.length || 0
                return (
                  <TableRow
                    key={student.student_id}
                    className="cursor-pointer"
                    onClick={(e) => {
                      // The name cell already has its own <Link> (for
                      // middle-click/ctrl-click "open in new tab" and for
                      // screen readers) - skip the extra navigate when the
                      // click originated on that link so it doesn't fire twice.
                      if (e.target.closest("a")) return
                      navigate(`/students/${student.student_id}`)
                    }}
                  >
                    <TableCell>
                      <Link to={`/students/${student.student_id}`} className="font-medium hover:underline">
                        {student.student_name || "Unnamed"}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{student.student_phone}</TableCell>
                    <TableCell className="text-muted-foreground">{student.course_interest || "—"}</TableCell>
                    <TableCell>
                      {concernCount > 0 ? (
                        <Badge variant="outline" className="gap-1 border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
                          <TriangleAlert className="size-3" />
                          {concernCount} concern{concernCount > 1 ? "s" : ""}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={band.className}>
                        {student.lead_score ?? 0} · {band.label}
                      </Badge>
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

function EmptyState({ title, description }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
      <GraduationCap className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
