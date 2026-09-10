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
    <div className="flex flex-col gap-8">
      <div className="relative overflow-hidden rounded-xl border bg-muted/20 p-6 sm:p-8">
        <div
          className="bg-dot-grid pointer-events-none absolute inset-x-[-10%] top-[-60%] h-[320px]"
          style={{
            maskImage: "radial-gradient(ellipse 55% 60% at 30% 100%, black 0%, transparent 75%)",
            WebkitMaskImage: "radial-gradient(ellipse 55% 60% at 30% 100%, black 0%, transparent 75%)",
          }}
        />
        <div className="relative">
          <h1 className="text-2xl font-semibold">Welcome back{user?.staff_name ? `, ${user.staff_name}` : ""}</h1>
          <p className="mt-1 text-muted-foreground">Here's what's happening at {college.college_name}.</p>
        </div>
      </div>

      {/* One hairline-bordered grid, not three separate shadow cards - the
          divider between columns does the same job the marketing site's
          problem/features grids do (frontend/home/index.html), so the
          dashboard's own "hero" moment reads as a continuation of that
          language rather than a switch to generic SaaS card chrome. */}
      <div className="grid overflow-hidden rounded-xl border sm:grid-cols-3 sm:divide-x">
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
    <Link
      to={to}
      className="group flex flex-col gap-3 border-t p-5 transition-colors first:border-t-0 hover:bg-accent/40 sm:border-t-0 sm:p-6"
    >
      <div className="flex items-center justify-between">
        <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-4.5" />
        </span>
        <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
      <div>
        <div className="font-display text-3xl font-semibold">
          {isLoading ? (
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          ) : isError ? (
            <span className="flex items-center gap-1.5 text-lg text-muted-foreground" title="Failed to load">
              <TriangleAlert className="size-5 text-warm" />
              {"\u2014"}
            </span>
          ) : (
            (count ?? 0)
          )}
        </div>
        <p className="mt-1 text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </Link>
  )
}
