import { Link } from "react-router-dom"
import { ExternalLink } from "lucide-react"
import { useStudentDetail } from "@/hooks/useStudents"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { leadScoreBand } from "@/lib/leadScore"

// Compact identity used inline in tables - name + phone + lead score, linking
// through to the full profile. Fetches via the same cached
// useStudentDetail hook the profile page uses, so once a staff member has
// opened a student once (from here, the students list, anywhere) it's
// instant everywhere else for the life of the session.
export function StudentSnapshot({ collegeId, studentId }) {
  const { data: student, isLoading, isError } = useStudentDetail(collegeId, studentId)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-3 w-20" />
      </div>
    )
  }

  if (isError || !student) {
    return <span className="text-sm text-muted-foreground">Student #{studentId}</span>
  }

  const band = leadScoreBand(student.lead_score ?? 0)

  return (
    <Link to={`/students/${studentId}`} className="group flex flex-col gap-0.5">
      <span className="font-medium group-hover:underline">{student.student_name || "Unnamed student"}</span>
      <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        {student.student_phone}
        <Badge variant="outline" className={`h-4 px-1 text-[10px] leading-none ${band.className}`}>
          {student.lead_score ?? 0} · {band.label}
        </Badge>
      </span>
    </Link>
  )
}

// Richer version for the reply dialog - same identity, plus course interest
// and an explicit "open full profile" link, since staff replying to a
// flagged question is exactly when they're most likely to want the wider
// context (past notes, signals, assignment) without losing their draft
// reply. Opens in a new tab for that reason.
export function StudentSnapshotCard({ collegeId, studentId }) {
  const { data: student, isLoading, isError } = useStudentDetail(collegeId, studentId)

  if (isLoading) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-md border p-3">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-24" />
        </div>
        <Skeleton className="h-5 w-16" />
      </div>
    )
  }

  if (isError || !student) {
    return (
      <div className="rounded-md border p-3 text-sm text-muted-foreground">
        Couldn't load student #{studentId}.
      </div>
    )
  }

  const band = leadScoreBand(student.lead_score ?? 0)

  return (
    <div className="flex items-start justify-between gap-3 rounded-md border p-3">
      <div className="flex flex-col gap-1 text-sm">
        <div className="flex items-center gap-2">
          <span className="font-medium">{student.student_name || "Unnamed student"}</span>
          <Badge variant="outline" className={band.className}>
            {student.lead_score ?? 0} · {band.label}
          </Badge>
        </div>
        <span className="text-muted-foreground">{student.student_phone}</span>
        {student.course_interest && (
          <span className="text-muted-foreground">Interested in {student.course_interest}</span>
        )}
      </div>
      <Link
        to={`/students/${studentId}`}
        target="_blank"
        rel="noreferrer"
        className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
      >
        Full profile
        <ExternalLink className="size-3" />
      </Link>
    </div>
  )
}
