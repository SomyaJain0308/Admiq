import { Link } from "react-router-dom"
import { Inbox, GraduationCap, Users, ArrowRight, Loader2, TriangleAlert } from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { useStudentList, useStudentLeadScores } from "@/hooks/useStudents"
import { useStaffList } from "@/hooks/useStaff"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { LeadScoreChart } from "@/components/LeadScoreChart"

export default function DashboardHome() {
  const { user } = useAuth()
  const { college, hasNoCollege } = useCurrentCollege()

  const queueQuery = useLowConfidenceQueries(college?.college_id, false)
  // Stat cards only need a total count, and the backend returns that
  // regardless of page size - pageSize: 1 gets it without pulling a page
  // of full records just to read one number.
  const studentsQuery = useStudentList(college?.college_id, { pageSize: 1 })
  const staffQuery = useStaffList(college?.college_id, { pageSize: 1 })
  // The lead-score chart needs every student's score, not full records, and
  // shouldn't silently truncate for colleges over 1000 students - so it
  // reads from its own lightweight endpoint instead of a big page of the
  // list above.
  const leadScoresQuery = useStudentLeadScores(college?.college_id)

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Welcome{user?.staff_name ? `, ${user.staff_name}` : ""}</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Welcome back{user?.staff_name ? `, ${user.staff_name}` : ""}</h1>
        <p className="text-muted-foreground">Here's what's happening at {college.college_name}.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          to="/queue"
          icon={Inbox}
          label="Waiting on you"
          count={queueQuery.data?.total}
          isLoading={queueQuery.isLoading}
          isError={queueQuery.isError}
          description="Low-confidence queries"
        />
        <StatCard
          to="/students"
          icon={GraduationCap}
          label="Students"
          count={studentsQuery.data?.total}
          isLoading={studentsQuery.isLoading}
          isError={studentsQuery.isError}
          description="Total conversations"
        />
        <StatCard
          to="/staff"
          icon={Users}
          label="Staff"
          count={staffQuery.data?.total}
          isLoading={staffQuery.isLoading}
          isError={staffQuery.isError}
          description="With access to this college"
        />
      </div>

      {leadScoresQuery.data?.lead_scores?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Lead score distribution</CardTitle>
            <CardDescription>Where your student pool currently sits, from cold to hot.</CardDescription>
          </CardHeader>
          <CardContent>
            <LeadScoreChart leadScores={leadScoresQuery.data.lead_scores} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function StatCard({ to, icon: Icon, label, count, isLoading, isError, description }) {
  return (
    <Link to={to}>
      <Card className="transition-colors hover:bg-accent/50">
        <CardHeader>
          <div className="flex items-center justify-between">
            <Icon className="size-5 text-muted-foreground" />
            <ArrowRight className="size-4 text-muted-foreground" />
          </div>
          <CardTitle className="pt-2 text-3xl font-semibold">
            {isLoading ? (
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            ) : isError ? (
              <span
                className="flex items-center gap-1.5 text-lg text-muted-foreground"
                title="Failed to load"
              >
                <TriangleAlert className="size-5 text-warm" />
                {"\u2014"}
              </span>
            ) : (
              (count ?? 0)
            )}
          </CardTitle>
          <CardDescription>{label}</CardDescription>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground">{description}</CardContent>
      </Card>
    </Link>
  )
}
