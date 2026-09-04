import { Link } from "react-router-dom"
import { Inbox, GraduationCap, Users, ArrowRight, Loader2, TriangleAlert } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { useStudentList } from "@/hooks/useStudents"
import { useStaffList } from "@/hooks/useStaff"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { LeadScoreChart } from "@/components/LeadScoreChart"
import { cn } from "@/lib/utils"

export default function DashboardHome() {
  const { user } = useAuth()
  const { college, hasNoCollege } = useCurrentCollege()

  const queueQuery = useLowConfidenceQueries(college?.college_id, false)
  // Stat cards just need a total count (the backend returns that regardless
  // of page size), but the lead-score chart below needs the full student
  // pool to build an accurate distribution - a big page size gets both from
  // one call rather than needing a separate "give me everyone" endpoint.
  const studentsQuery = useStudentList(college?.college_id, { pageSize: 1000 })
  const staffQuery = useStaffList(college?.college_id, { pageSize: 1000 })

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
        <h1 className="text-2xl font-semibold">
          Welcome back{user?.staff_name ? <>, <span className="text-gradient-brand">{user.staff_name}</span></> : ""}
        </h1>
        <p className="mt-1 text-muted-foreground">Here's what's happening at {college.college_name}.</p>
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
          accent="primary"
        />
        <StatCard
          to="/students"
          icon={GraduationCap}
          label="Students"
          count={studentsQuery.data?.total}
          isLoading={studentsQuery.isLoading}
          isError={studentsQuery.isError}
          description="Total conversations"
          accent="brand-2"
        />
        <StatCard
          to="/staff"
          icon={Users}
          label="Staff"
          count={staffQuery.data?.total}
          isLoading={staffQuery.isLoading}
          isError={staffQuery.isError}
          description="With access to this college"
          accent="teal"
        />
      </div>

      {studentsQuery.data?.items?.length > 0 && (
        <Card className="overflow-hidden">
          <div className="-mt-6 h-1 bg-gradient-brand" />
          <CardHeader>
            <CardTitle className="text-base">Lead score distribution</CardTitle>
            <CardDescription>Where your student pool currently sits, from cold to hot.</CardDescription>
          </CardHeader>
          <CardContent>
            <LeadScoreChart students={studentsQuery.data.items} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// Each card gets its own hue (brand blue / violet / teal) purely for
// visual variety across the row - they aren't semantically tied to
// anything (unlike the hot/warm/cold lead-temperature colors), so picking
// three distinct, deliberately-chosen brand hues reads as richer than
// three identical blue icons in a row.
const ACCENTS = {
  primary: {
    chip: "bg-primary/12 text-primary",
    bar: "bg-primary",
  },
  "brand-2": {
    chip: "bg-brand-2/12 text-brand-2",
    bar: "bg-brand-2",
  },
  teal: {
    chip: "bg-teal/12 text-teal",
    bar: "bg-teal",
  },
}

function StatCard({ to, icon: Icon, label, count, isLoading, isError, description, accent = "primary" }) {
  const { chip, bar } = ACCENTS[accent]
  return (
    <Link to={to} className="group block">
      <Card className="overflow-hidden transition-all duration-150 ease-[var(--ease-out)] group-hover:-translate-y-0.5 group-hover:border-ring/30 group-hover:shadow-[var(--shadow-md)]">
        <div className={cn("-mt-6 h-1", bar)} />
        <CardHeader>
          <div className="flex items-center justify-between">
            <span className={cn("flex size-9 items-center justify-center rounded-lg", chip)}>
              <Icon className="size-4.5" />
            </span>
            <ArrowRight className="size-4 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-foreground" />
          </div>
          <CardTitle className="font-display pt-3 text-3xl font-semibold tabular-nums">
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
