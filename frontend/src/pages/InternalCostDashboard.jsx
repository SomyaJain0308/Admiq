import { useState } from "react"
import {
  Loader2,
  TriangleAlert,
  ShieldAlert,
  DollarSign,
  Users,
  MessagesSquare,
  ArrowUpRight,
  ArrowDownRight,
  Lock,
} from "lucide-react"
import { useInternalCostStats } from "@/hooks/useInternalCostStats"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table"
import { cn } from "@/lib/utils"

// -----------------------------------------------------------------------
// INTERNAL / ADMIQ-STAFF ONLY.
//
// This page is not linked from DashboardLayout's nav and is not reachable
// through college-staff login - it talks directly to
// backend/app/api/v1/routers/costs.py's /internal/costs/{college_id}/stats,
// which is gated by X-Cost-Reporting-Token (a separate shared secret from
// the JWT college staff use) and deliberately excluded from
// verify_college_access. That endpoint's own docstring is explicit: this is
// internal margin data, and the existing customer-facing dashboard should
// never be pointed at it. Keep this page unlinked and out of
// DashboardLayout for the same reason - if you need a customer-facing usage
// view, build a separate, deliberately-limited endpoint for that instead of
// loosening this one.
// -----------------------------------------------------------------------

function formatUsd(value) {
  if (value == null || Number.isNaN(value)) return "\u2014"
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 4 : 2,
  }).format(value)
}

function formatPercent(value) {
  if (value == null || Number.isNaN(value)) return "\u2014"
  return `${value.toFixed(1)}%`
}

function StatTile({ icon: Icon, label, value, sublabel }) {
  return (
    <div className="flex flex-col gap-1 border-t p-5 first:border-t-0 sm:border-t-0 sm:border-l sm:p-6 sm:first:border-l-0">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        {Icon && <Icon className="size-3.5" />}
        {label}
      </p>
      <div className="font-display text-2xl font-semibold tracking-tight">{value}</div>
      {sublabel && <p className="text-xs text-muted-foreground">{sublabel}</p>}
    </div>
  )
}

function WeekOverWeekBadge({ current, previous }) {
  if (!previous) return null
  const delta = ((current - previous) / previous) * 100
  const isUp = delta >= 0
  return (
    <Badge variant="outline" className={cn("gap-1", isUp ? "text-warm" : "text-emerald-600")}>
      {isUp ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
      {Math.abs(delta).toFixed(1)}% vs prior week
    </Badge>
  )
}

// Small gate so the token never sits in component state before the person
// has deliberately typed it in, and never gets auto-submitted - unlike the
// staff login form, there's no "remember me" here on purpose.
function AccessGate({ onSubmit, error }) {
  const [collegeId, setCollegeId] = useState("")
  const [token, setToken] = useState("")

  function handleSubmit(e) {
    e.preventDefault()
    if (!collegeId || !token) return
    onSubmit(collegeId.trim(), token.trim())
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-6 px-4">
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="flex size-10 items-center justify-center rounded-full bg-muted">
          <Lock className="size-5 text-muted-foreground" />
        </div>
        <h1 className="font-display text-lg font-semibold">Internal cost reporting</h1>
        <p className="text-sm text-muted-foreground">
          Admiq-staff only. Requires the college's numeric ID and the cost reporting token
          (<code className="rounded bg-muted px-1 py-0.5 text-xs">COST_REPORTING_TOKEN</code> in the backend env).
        </p>
      </div>
      <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="college-id">College ID</Label>
          <Input id="college-id" inputMode="numeric" value={collegeId} onChange={(e) => setCollegeId(e.target.value)} placeholder="e.g. 4" required />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cost-token">X-Cost-Reporting-Token</Label>
          <Input id="cost-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste token" required autoComplete="off" />
        </div>
        {error && (
          <p className="flex items-center gap-1.5 text-sm text-destructive">
            <TriangleAlert className="size-4" />
            {error}
          </p>
        )}
        <Button type="submit" className="w-full">
          View cost stats
        </Button>
      </form>
    </div>
  )
}

export default function InternalCostDashboard() {
  const [session, setSession] = useState(null) // { collegeId, token } once submitted

  const { data: stats, isLoading, isError, error } = useInternalCostStats(session?.collegeId, session?.token)

  if (!session) {
    return <AccessGate onSubmit={(collegeId, token) => setSession({ collegeId, token })} />
  }

  // A 401 means the token itself was wrong (or unconfigured server-side) -
  // drop back to the gate rather than sitting on a permanently-broken
  // query, since retry:false means it won't self-heal.
  if (isError && error?.status === 401) {
    return <AccessGate onSubmit={(collegeId, token) => setSession({ collegeId, token })} error="Invalid or missing token. Try again." />
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-semibold tracking-tight">Cost reporting \u2014 College #{session.collegeId}</h1>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
            <ShieldAlert className="size-4" />
            Internal margin data. Not visible to college staff.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setSession(null)}>
          Switch college / token
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          <Loader2 className="size-5 animate-spin" />
        </div>
      )}

      {isError && error?.status !== 401 && (
        <Card>
          <CardContent className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <TriangleAlert className="size-4 text-warm" />
            Couldn't load cost stats ({error?.message || "unknown error"}).
          </CardContent>
        </Card>
      )}

      {stats && (
        <div className="flex flex-col gap-6">
          {/* ---- Headline spend ---- */}
          <div className="shadow-elevated grid overflow-hidden rounded-xl border sm:grid-cols-3">
            <StatTile icon={DollarSign} label="Total spend, all time" value={formatUsd(stats.total_cost_usd_all_time)} />
            <StatTile
              icon={DollarSign}
              label="Last 7 days"
              value={formatUsd(stats.total_cost_usd_last_7_days)}
              sublabel={<WeekOverWeekBadge current={stats.total_cost_usd_last_7_days} previous={stats.total_cost_usd_prev_7_days} />}
            />
            <StatTile icon={DollarSign} label="Prior 7 days" value={formatUsd(stats.total_cost_usd_prev_7_days)} />
          </div>

          {/* ---- Per-student unit economics ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="size-4" />
                Cost per student
              </CardTitle>
              <CardDescription>
                Across all {stats.total_students.toLocaleString()} students at this college \u2014 including the ones who never
                engaged, counted as $0. That's the honest denominator for "what does a student cost us."
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Average</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.avg_cost_per_student_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Median</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.median_cost_per_student_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">p95 (expensive tail)</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.p95_cost_per_student_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Total students</p>
                  <p className="font-display text-xl font-semibold">{stats.total_students.toLocaleString()}</p>
                </div>
              </div>

              {stats.top_students_by_cost.length > 0 && (
                <div className="mt-6">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Costliest students, all time</p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Student</TableHead>
                        <TableHead className="text-right">Total cost</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {stats.top_students_by_cost.map((s) => (
                        <TableRow key={s.student_id}>
                          <TableCell>{s.student_name || `Student #${s.student_id}`}</TableCell>
                          <TableCell className="text-right font-medium">{formatUsd(s.total_cost_usd)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* ---- Per-session unit economics ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessagesSquare className="size-4" />
                Cost per session
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Total sessions</p>
                  <p className="font-display text-xl font-semibold">{stats.total_sessions.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Average</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.avg_cost_per_session_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Median</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.median_cost_per_session_usd)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ---- Escalation efficiency ---- */}
          <Card>
            <CardHeader>
              <CardTitle>Low-confidence escalations</CardTitle>
              <CardDescription>How much pricier a session gets once it hits the low-confidence queue.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Sessions escalated</p>
                  <p className="font-display text-xl font-semibold">{stats.sessions_with_low_confidence_escalation.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Avg cost, escalated</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.avg_cost_per_escalated_session_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Avg cost, self-served</p>
                  <p className="font-display text-xl font-semibold">{formatUsd(stats.avg_cost_per_non_escalated_session_usd)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ---- Breakdowns ---- */}
          <div className="grid gap-6 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Cost by type</CardTitle>
                <CardDescription>LLM vs embedding vs WhatsApp, share of all-time spend.</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                      <TableHead className="text-right">Share</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stats.cost_by_type.map((row) => (
                      <TableRow key={row.cost_type}>
                        <TableCell className="capitalize">{row.cost_type}</TableCell>
                        <TableCell className="text-right">{formatUsd(row.total_cost_usd)}</TableCell>
                        <TableCell className="text-right text-muted-foreground">{formatPercent(row.percent_of_total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Cost by stage</CardTitle>
                <CardDescription>Top stages by spend \u2014 where retries or fallback are burning money.</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Stage</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                      <TableHead className="text-right">Tokens</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stats.cost_by_stage.map((row) => (
                      <TableRow key={row.stage}>
                        <TableCell>{row.stage}</TableCell>
                        <TableCell className="text-right">{formatUsd(row.total_cost_usd)}</TableCell>
                        <TableCell className="text-right text-muted-foreground">{row.total_tokens.toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
