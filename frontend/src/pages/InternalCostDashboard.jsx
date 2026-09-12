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
  TrendingUp,
  Cpu,
  BookOpen,
  Send,
  MessageCircle,
} from "lucide-react"
import { useInternalCostStats } from "@/hooks/useInternalCostStats"
import { useInternalCollegeList } from "@/hooks/useInternalCollegeList"
import { useInternalStudentCostEvents } from "@/hooks/useInternalStudentCostEvents"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { cn, nativeSelectClassName } from "@/lib/utils"

// Approximate as of when this page was built (Sep 2026) - USD/INR moves
// daily, so this is only a starting point. Editable in the currency
// control below; not fetched live since a live-rate API is one more
// external dependency this internal-only page doesn't need.
const DEFAULT_USD_TO_INR_RATE = 93

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

function formatCurrencyValue(usdValue, currency, inrRate) {
  if (usdValue == null || Number.isNaN(usdValue)) return "\u2014"
  if (currency === "INR") {
    const inrValue = usdValue * (inrRate || 0)
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      minimumFractionDigits: inrValue < 1 ? 4 : 2,
      maximumFractionDigits: inrValue < 1 ? 4 : 2,
    }).format(inrValue)
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: usdValue < 1 ? 4 : 2,
    maximumFractionDigits: usdValue < 1 ? 4 : 2,
  }).format(usdValue)
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

// Hand-rolled bar chart, same reasoning as components/LeadScoreChart.jsx:
// one chart on this page doesn't justify recharts' ~350kB (gzip ~100kB),
// and 30 flexbox columns render this exactly as well.
function DailyCostTrendChart({ daily, fmt }) {
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const maxCost = Math.max(0.01, ...daily.map((d) => d.total_cost_usd))

  return (
    // Composite chart, summarized as one unit for screen readers - same
    // role="img" pattern LeadScoreChart uses for the same reason.
    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
    <div className="flex h-[140px] items-end gap-[3px]" role="img" aria-label="Bar chart of daily cost over the trailing 30 days">
      {daily.map((d, i) => (
        <button
          key={d.date}
          type="button"
          className="relative flex h-full flex-1 flex-col items-center justify-end gap-1 rounded-sm border-0 bg-transparent p-0 outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          onMouseEnter={() => setHoveredIndex(i)}
          onMouseLeave={() => setHoveredIndex(null)}
          onFocus={() => setHoveredIndex(i)}
          onBlur={() => setHoveredIndex(null)}
          aria-label={`${d.date}: ${fmt(d.total_cost_usd)}`}
        >
          {hoveredIndex === i && (
            <div className="pointer-events-none absolute bottom-full z-10 mb-1.5 flex flex-col items-center rounded-md border bg-popover px-2 py-1 text-xs whitespace-nowrap text-popover-foreground shadow-md">
              <span className="font-medium">{fmt(d.total_cost_usd)}</span>
              <span className="text-[10px] text-muted-foreground">{d.date}</span>
            </div>
          )}
          <div
            className="w-full rounded-t-sm bg-primary transition-[opacity] duration-150"
            style={{
              height: `${(d.total_cost_usd / maxCost) * 100}%`,
              minHeight: d.total_cost_usd > 0 ? "2px" : 0,
              opacity: hoveredIndex === null || hoveredIndex === i ? 1 : 0.4,
            }}
          />
        </button>
      ))}
    </div>
  )
}

// Small gate so the token never sits in component state before the person
// has deliberately typed it in, and never gets auto-submitted - unlike the
// staff login form, there's no "remember me" here on purpose.
function AccessGate({ onSubmit, error }) {
  const [collegeId, setCollegeId] = useState("")
  const [token, setToken] = useState("")
  const [adminToken, setAdminToken] = useState("")
  // Only actually fires the /router/college request once this is true, and
  // only after the person clicks "Load colleges" - see useInternalCollegeList.
  const [collegesRequested, setCollegesRequested] = useState(false)

  const collegeList = useInternalCollegeList(adminToken, { enabled: collegesRequested })

  function handleLoadColleges(e) {
    e.preventDefault()
    if (!adminToken) return
    setCollegesRequested(true)
  }

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

      {/* Optional: look colleges up by name instead of typing a raw ID.
          Separate token on purpose - see useInternalCollegeList.js - so
          someone with only the cost-reporting token still can't list every
          college's name/contact info. */}
      <div className="flex w-full flex-col gap-2 rounded-lg border border-dashed p-3">
        <Label htmlFor="admin-token" className="text-xs text-muted-foreground">
          Optional: X-Admin-Token, to pick a college by name
        </Label>
        <div className="flex gap-2">
          <Input
            id="admin-token"
            type="password"
            value={adminToken}
            onChange={(e) => {
              setAdminToken(e.target.value)
              setCollegesRequested(false)
            }}
            placeholder="Paste admin token"
            autoComplete="off"
            className="h-8 text-sm"
          />
          <Button type="button" variant="outline" size="sm" onClick={handleLoadColleges} disabled={!adminToken}>
            Load
          </Button>
        </div>
        {collegeList.isLoading && <p className="text-xs text-muted-foreground">Loading colleges\u2026</p>}
        {collegeList.isError && <p className="text-xs text-destructive">Couldn't load colleges ({collegeList.error?.message}).</p>}
        {collegeList.data && (
          <select
            className={cn(nativeSelectClassName, "w-full")}
            value={collegeId}
            onChange={(e) => setCollegeId(e.target.value)}
          >
            <option value="">Select a college\u2026</option>
            {collegeList.data.map((college) => (
              <option key={college.college_id} value={college.college_id}>
                {college.college_name} (#{college.college_id})
              </option>
            ))}
          </select>
        )}
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

// USD/INR toggle plus an editable rate - kept as a small standalone control
// rather than baked into the header markup so it's easy to see it's just
// UI-level conversion: the underlying numbers from the API are always USD
// (that's what Google actually bills in), this only changes display.
function CurrencyControl({ currency, onCurrencyChange, inrRate, onRateChange }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex rounded-md border p-0.5">
        <button
          type="button"
          onClick={() => onCurrencyChange("USD")}
          className={cn("rounded px-2.5 py-1 text-xs font-medium transition-colors", currency === "USD" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          USD
        </button>
        <button
          type="button"
          onClick={() => onCurrencyChange("INR")}
          className={cn("rounded px-2.5 py-1 text-xs font-medium transition-colors", currency === "INR" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          INR
        </button>
      </div>
      {currency === "INR" && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span>1 USD =</span>
          <Input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            value={inrRate}
            onChange={(e) => onRateChange(e.target.value === "" ? "" : Number(e.target.value))}
            className="h-7 w-20 text-xs"
          />
          <span>INR</span>
        </div>
      )}
    </div>
  )
}

// Per-student drill-down: every raw cost_events row, so "I only asked one
// question but it cost $X" can actually be checked against what fired -
// resolve_query/re_query/retrieval_embedding/primary/fallback can all bill
// separately for a single message. See costs.py's get_student_cost_events.
function StudentEventsDialog({ student, collegeId, token, fmt, open, onOpenChange }) {
  const { data: events, isLoading, isError, error } = useInternalStudentCostEvents(collegeId, student?.student_id, token, { enabled: open })
  const total = events?.reduce((sum, e) => sum + e.cost_usd, 0) ?? 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{student?.student_name || `Student #${student?.student_id}`} \u2014 cost events</DialogTitle>
          <DialogDescription>
            {events ? `${events.length} event${events.length === 1 ? "" : "s"}, most recent first, totaling ${fmt(total)}.` : "Every billed call recorded for this student."}
            {events && events.length === 200 && " (capped at 200 - this student has more history than that.)"}
          </DialogDescription>
        </DialogHeader>
        {isLoading && (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        )}
        {isError && (
          <p className="flex items-center gap-1.5 py-4 text-sm text-destructive">
            <TriangleAlert className="size-4" />
            Couldn't load events ({error?.message || "unknown error"}).
          </p>
        )}
        {events && (
          <div className="max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Stage</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Tokens</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((e) => (
                  <TableRow key={e.cost_event_id}>
                    <TableCell className="text-xs whitespace-nowrap text-muted-foreground">{new Date(e.created_at).toLocaleString()}</TableCell>
                    <TableCell className="text-xs">{e.stage || "\u2014"}</TableCell>
                    <TableCell className="text-xs">{e.model || "\u2014"}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">{(e.input_tokens + e.output_tokens).toLocaleString()}</TableCell>
                    <TableCell className="text-right text-xs font-medium">{fmt(e.cost_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default function InternalCostDashboard() {
  const [session, setSession] = useState(null) // { collegeId, token } once submitted
  const [currency, setCurrency] = useState("USD")
  const [inrRate, setInrRate] = useState(DEFAULT_USD_TO_INR_RATE)
  const [selectedStudent, setSelectedStudent] = useState(null) // drives StudentEventsDialog

  const { data: stats, isLoading, isError, error } = useInternalCostStats(session?.collegeId, session?.token)

  const fmt = (usdValue) => formatCurrencyValue(usdValue, currency, inrRate)

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
        <div className="flex flex-wrap items-center gap-3">
          <CurrencyControl currency={currency} onCurrencyChange={setCurrency} inrRate={inrRate} onRateChange={setInrRate} />
          <Button variant="outline" size="sm" onClick={() => setSession(null)}>
            Switch college / token
          </Button>
        </div>
      </div>

      <StudentEventsDialog
        student={selectedStudent}
        collegeId={session.collegeId}
        token={session.token}
        fmt={fmt}
        open={!!selectedStudent}
        onOpenChange={(open) => !open && setSelectedStudent(null)}
      />

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
            <StatTile icon={DollarSign} label="Total spend, all time" value={fmt(stats.total_cost_usd_all_time)} />
            <StatTile
              icon={DollarSign}
              label="Last 7 days"
              value={fmt(stats.total_cost_usd_last_7_days)}
              sublabel={<WeekOverWeekBadge current={stats.total_cost_usd_last_7_days} previous={stats.total_cost_usd_prev_7_days} />}
            />
            <StatTile icon={DollarSign} label="Prior 7 days" value={fmt(stats.total_cost_usd_prev_7_days)} />
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
                  <p className="font-display text-xl font-semibold">{fmt(stats.avg_cost_per_student_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Median</p>
                  <p className="font-display text-xl font-semibold">{fmt(stats.median_cost_per_student_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">p95 (expensive tail)</p>
                  <p className="font-display text-xl font-semibold">{fmt(stats.p95_cost_per_student_usd)}</p>
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
                        <TableHead className="w-0" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {stats.top_students_by_cost.map((s) => (
                        <TableRow key={s.student_id}>
                          <TableCell>{s.student_name || `Student #${s.student_id}`}</TableCell>
                          <TableCell className="text-right font-medium">{fmt(s.total_cost_usd)}</TableCell>
                          <TableCell className="text-right">
                            <Button variant="ghost" size="sm" onClick={() => setSelectedStudent(s)}>
                              View
                            </Button>
                          </TableCell>
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
                  <p className="font-display text-xl font-semibold">{fmt(stats.avg_cost_per_session_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Median</p>
                  <p className="font-display text-xl font-semibold">{fmt(stats.median_cost_per_session_usd)}</p>
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
                  <p className="font-display text-xl font-semibold">{fmt(stats.avg_cost_per_escalated_session_usd)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Avg cost, self-served</p>
                  <p className="font-display text-xl font-semibold">{fmt(stats.avg_cost_per_non_escalated_session_usd)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ---- Trend ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="size-4" />
                Daily spend, trailing 30 days
              </CardTitle>
              <CardDescription>
                Run-rate if the last 7 days repeat all month: <span className="font-medium text-foreground">{fmt(stats.projected_monthly_cost_usd)}</span>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <DailyCostTrendChart daily={stats.daily_cost_last_30_days} fmt={fmt} />
            </CardContent>
          </Card>

          {/* ---- Per-reply & knowledge-base overhead ---- */}
          <div className="shadow-elevated grid overflow-hidden rounded-xl border sm:grid-cols-3">
            <StatTile icon={Send} label="Avg cost per assistant reply" value={fmt(stats.avg_cost_per_assistant_message_usd)} />
            <StatTile
              icon={BookOpen}
              label="Knowledge base (ingestion) cost"
              value={fmt(stats.document_ingestion_cost_usd)}
              sublabel={`${stats.document_count.toLocaleString()} document${stats.document_count === 1 ? "" : "s"}`}
            />
            <StatTile icon={BookOpen} label="Avg cost per document" value={fmt(stats.avg_cost_per_document_usd)} />
          </div>

          {/* ---- Cost by model & WhatsApp breakdown ---- */}
          <div className="grid gap-6 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Cpu className="size-4" />
                  Cost by model
                </CardTitle>
                <CardDescription>LLM and embedding spend by underlying model, highest first.</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Model</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                      <TableHead className="text-right">Tokens</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {stats.cost_by_model.map((row) => (
                      <TableRow key={row.model}>
                        <TableCell>{row.model}</TableCell>
                        <TableCell className="text-right">{fmt(row.total_cost_usd)}</TableCell>
                        <TableCell className="text-right text-muted-foreground">{row.total_tokens.toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MessageCircle className="size-4" />
                  WhatsApp cost by category
                </CardTitle>
                <CardDescription>Session (free-form reply) vs utility/marketing (template-triggered) sends.</CardDescription>
              </CardHeader>
              <CardContent>
                {stats.whatsapp_cost_breakdown.length === 0 ? (
                  <p className="py-4 text-sm text-muted-foreground">No billed WhatsApp sends yet.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Category</TableHead>
                        <TableHead className="text-right">Cost</TableHead>
                        <TableHead className="text-right">Sends</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {stats.whatsapp_cost_breakdown.map((row) => (
                        <TableRow key={row.category}>
                          <TableCell className="capitalize">{row.category}</TableCell>
                          <TableCell className="text-right">{fmt(row.total_cost_usd)}</TableCell>
                          <TableCell className="text-right text-muted-foreground">{row.message_count.toLocaleString()}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

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
                        <TableCell className="text-right">{fmt(row.total_cost_usd)}</TableCell>
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
                        <TableCell className="text-right">{fmt(row.total_cost_usd)}</TableCell>
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
