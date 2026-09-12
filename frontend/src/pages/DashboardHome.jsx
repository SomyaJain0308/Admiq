import { useState } from "react"
import { Link } from "react-router-dom"
import {
  Inbox,
  GraduationCap,
  Users,
  ArrowRight,
  Loader2,
  TriangleAlert,
  Flame,
} from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { useStudentList, useStudentLeadScores } from "@/hooks/useStudents"
import { useStaffList } from "@/hooks/useStaff"
import { useDashboardStats } from "@/hooks/useDashboardStats"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { LeadScoreChart } from "@/components/LeadScoreChart"
import { StudentSnapshot } from "@/components/StudentSnapshot"
import { ReplyToQueryDialog } from "@/components/ReplyToQueryDialog"
import { PerformanceStatsRow, MessageActivityCard, LeadFunnelCard, StaffLeaderboardCard, KnowledgeBaseHealthCard } from "@/components/DashboardMetrics"
import { leadScoreBand } from "@/lib/leadScore"
import { timeSince } from "@/lib/formatTime"
import { cn } from "@/lib/utils"

// How many rows each preview widget shows before pointing staff at the full
// page - small enough to scan at a glance, big enough to actually be useful
// without opening anything.
const PREVIEW_SIZE = 5

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
  const dashboardStatsQuery = useDashboardStats(college?.college_id)

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Welcome{user?.staff_name ? `, ${user.staff_name}` : ""}</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="bg-glow-primary shadow-elevated relative overflow-hidden rounded-xl border bg-muted/20 p-6 sm:p-8">
        <div
          className="bg-dot-grid pointer-events-none absolute inset-x-[-10%] top-[-60%] h-[320px]"
          style={{
            maskImage: "radial-gradient(ellipse 55% 60% at 30% 100%, black 0%, transparent 75%)",
            WebkitMaskImage: "radial-gradient(ellipse 55% 60% at 30% 100%, black 0%, transparent 75%)",
          }}
        />
        <div className="relative">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Welcome back{user?.staff_name ? `, ${user.staff_name}` : ""}
          </h1>
          <p className="mt-1.5 text-muted-foreground">Here's what's happening at {college.college_name}.</p>
        </div>
      </div>

      {/* One hairline-bordered grid, not three separate shadow cards - the
          divider between columns does the same job the marketing site's
          problem/features grids do (frontend/home/index.html), so the
          dashboard's own "hero" moment reads as a continuation of that
          language rather than a switch to generic SaaS card chrome. A single
          shadow-elevated on the outer grid (not per-cell) keeps that one
          shared surface instead of three competing floating boxes. */}
      <div className="shadow-elevated grid overflow-hidden rounded-xl border sm:grid-cols-3 sm:divide-x">
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

      <PerformanceStatsRow stats={dashboardStatsQuery.data} isLoading={dashboardStatsQuery.isLoading} isError={dashboardStatsQuery.isError} />

      <div className="grid gap-6 lg:grid-cols-2">
        <NeedsAttentionCard collegeId={college?.college_id} />
        <HotLeadsCard collegeId={college?.college_id} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <MessageActivityCard stats={dashboardStatsQuery.data} isLoading={dashboardStatsQuery.isLoading} isError={dashboardStatsQuery.isError} />
        <LeadFunnelCard stats={dashboardStatsQuery.data} isLoading={dashboardStatsQuery.isLoading} isError={dashboardStatsQuery.isError} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <StaffLeaderboardCard stats={dashboardStatsQuery.data} isLoading={dashboardStatsQuery.isLoading} isError={dashboardStatsQuery.isError} />
        <KnowledgeBaseHealthCard stats={dashboardStatsQuery.data} isLoading={dashboardStatsQuery.isLoading} isError={dashboardStatsQuery.isError} />
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
      className="group relative flex flex-col gap-3 border-t p-5 transition-colors first:border-t-0 hover:bg-accent/40 sm:border-t-0 sm:p-6"
    >
      <div className="flex items-center justify-between">
        <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
          <Icon className="size-4.5" />
        </span>
        <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
      </div>
      <div>
        <div className="font-display text-4xl font-semibold tracking-tight">
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
        <p className="mt-1.5 text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
    </Link>
  )
}

// Oldest-waiting open queries, straight from the queue's own default sort -
// the point isn't a different view of the data, it's not having to leave
// Overview to act on it, so replying opens the exact same dialog the queue
// page itself uses.
function NeedsAttentionCard({ collegeId }) {
  const [activeQuery, setActiveQuery] = useState(null)
  const { data, isLoading, isError } = useLowConfidenceQueries(collegeId, false, { page: 1, pageSize: PREVIEW_SIZE })
  const queries = data?.items || []
  const total = data?.total ?? 0

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Needs your attention</CardTitle>
            <CardDescription>Longest-waiting questions the assistant couldn't answer on its own.</CardDescription>
          </div>
          {total > 0 && (
            <Badge variant="destructive" className="shrink-0 rounded-full">
              {total}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {isLoading && (
          <div className="flex items-center justify-center py-6 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
          </div>
        )}
        {isError && <p className="py-4 text-sm text-muted-foreground">Couldn't load the queue.</p>}
        {!isLoading && !isError && queries.length === 0 && (
          <p className="py-4 text-sm text-muted-foreground">Nothing waiting on you right now.</p>
        )}
        {queries.map((query) => (
          <div key={query.query_id} className="flex items-center gap-3 border-t py-3 first:border-t-0">
            <div className="min-w-0 flex-1">
              <StudentSnapshot collegeId={collegeId} studentId={query.student_id} />
              <p className="mt-1 truncate text-sm text-muted-foreground" title={query.question_content}>
                {query.question_content}
              </p>
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">{timeSince(query.flagged_at)}</span>
            <Button size="sm" variant="outline" className="shrink-0" onClick={() => setActiveQuery(query)}>
              Reply
            </Button>
          </div>
        ))}
      </CardContent>
      {total > queries.length && (
        <div className="border-t px-6 pt-4">
          <Link to="/queue" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
            View all {total} in the queue
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      )}

      <ReplyToQueryDialog
        query={activeQuery}
        collegeId={collegeId}
        open={!!activeQuery}
        onOpenChange={(open) => !open && setActiveQuery(null)}
      />
    </Card>
  )
}

// The hottest N leads, straight from the students list's own default sort
// (highest lead_score first) - no separate query logic to keep in sync with
// what "hot" means on the Students page itself.
function HotLeadsCard({ collegeId }) {
  const { data, isLoading, isError } = useStudentList(collegeId, { pageSize: PREVIEW_SIZE })
  const students = data?.items || []

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="icon-badge-hot flex size-7 items-center justify-center rounded-full">
            <Flame className="size-4" />
          </span>
          <div>
            <CardTitle className="text-base">Hottest leads right now</CardTitle>
            <CardDescription>Highest lead score across every student in conversation.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {isLoading && (
          <div className="flex items-center justify-center py-6 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
          </div>
        )}
        {isError && <p className="py-4 text-sm text-muted-foreground">Couldn't load students.</p>}
        {!isLoading && !isError && students.length === 0 && (
          <p className="py-4 text-sm text-muted-foreground">No students yet - they'll show up here once they message on WhatsApp.</p>
        )}
        {students.map((student) => {
          const band = leadScoreBand(student.lead_score ?? 0)
          return (
            <Link
              key={student.student_id}
              to={`/students/${student.student_id}`}
              className="group flex items-center gap-3 border-t py-3 first:border-t-0"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium group-hover:underline">{student.student_name || "Unnamed student"}</p>
                <p className="truncate text-xs text-muted-foreground">{student.course_interest || student.student_phone}</p>
              </div>
              <Badge variant="outline" className={cn("shrink-0 font-display", band.className)}>
                {student.lead_score ?? 0} · {band.label}
              </Badge>
            </Link>
          )
        })}
      </CardContent>
      {students.length > 0 && (
        <div className="border-t px-6 pt-4">
          <Link to="/students" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
            View all students
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      )}
    </Card>
  )
}
