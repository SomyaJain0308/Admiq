import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { GraduationCap, Search, TriangleAlert } from "lucide-react"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useStudentList } from "@/hooks/useStudents"
import { usePagination } from "@/hooks/usePagination"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
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

export default function StudentsList() {
  const { college, hasNoCollege } = useCurrentCollege()
  const { data: students, isLoading, isError, error } = useStudentList(college?.college_id)
  const [search, setSearch] = useState("")

  const sortedStudents = useMemo(() => {
    if (!students) return []
    const query = search.trim().toLowerCase()
    const filtered = query
      ? students.filter(
          (s) =>
            s.student_name?.toLowerCase().includes(query) ||
            s.student_phone?.toLowerCase().includes(query) ||
            s.course_interest?.toLowerCase().includes(query)
        )
      : students
    return [...filtered].sort((a, b) => (b.lead_score ?? 0) - (a.lead_score ?? 0))
  }, [students, search])

  const { page, setPage, totalPages, pageItems } = usePagination(sortedStudents, 15)

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
        {students?.length > 0 && (
          <div className="relative w-full sm:w-64">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search name, phone, course..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
        )}
      </div>

      {isError && (
        <p className="text-sm text-destructive">
          {error?.message || "Failed to load students. Please try again."}
        </p>
      )}

      {!isLoading && !isError && students?.length === 0 && (
        <EmptyState title="No students yet" description="Students will show up here once they message your WhatsApp number." />
      )}

      {!isLoading && students?.length > 0 && sortedStudents.length === 0 && (
        <p className="text-sm text-muted-foreground">No students match "{search}".</p>
      )}

      {(isLoading || pageItems.length > 0) && (
        <Table>
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
              pageItems.map((student) => {
                const band = leadScoreBand(student.lead_score ?? 0)
                const concernCount = student.profile_signals?.concerns?.length || 0
                return (
                  <TableRow key={student.student_id} className="cursor-pointer">
                    <TableCell>
                      <Link to={`/students/${student.student_id}`} className="hover:underline">
                        {student.student_name || "Unnamed"}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{student.student_phone}</TableCell>
                    <TableCell className="text-muted-foreground">{student.course_interest || "—"}</TableCell>
                    <TableCell>
                      {concernCount > 0 ? (
                        <Badge variant="outline" className="gap-1 border-amber-200 bg-amber-50 text-amber-700">
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
