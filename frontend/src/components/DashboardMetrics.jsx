import { Link } from "react-router-dom"
import { ArrowRight, ArrowUpRight, ArrowDownRight, Loader2, TriangleAlert, Trophy, BookOpen, FileWarning, Star, MessagesSquare, UserX } from "lucide-react"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { formatDuration } from "@/lib/formatTime"
import { cn } from "@/lib/utils"

// Shared loading/error/empty states so every metric block on Overview
// handles a slow or failed dashboard-stats fetch the same way, rather than
// each card growing its own slightly-different version of the same guard.
function MetricBlockStatus({ isLoading, isError, isEmpty, emptyMessage }) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
      </div>
    )
  }
  if (isError) {
    return <p className="py-4 text-sm text-muted-foreground">Couldn't load this right now.</p>
  }
  if (isEmpty) {
    return <p className="py-4 text-sm text-muted-foreground">{emptyMessage}</p>
  }
  return null
}

// A compact number-first stat, several to a row, distinct from the bigger
// top-of-page StatCard trio - these aren't primary navigation targets, just
// quick-scan numbers, so they skip the icon chip and hover-to-navigate
// affordance those cards use.
function MiniStat({ label, value, isLoading, isError, sublabel }) {
  return (
    <div className="flex flex-col gap-1 border-t p-5 first:border-t-0 sm:border-t-0 sm:border-l sm:p-6 sm:first:border-l-0">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="font-display text-2xl font-semibold tracking-tight">
        {isLoading ? (
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        ) : isError ? (
          <span className="flex items-center gap-1.5 text-base text-muted-foreground" title="Failed to load">
            <TriangleAlert className="size-4 text-warm" />
            {"\u2014"}
          </span>
        ) : (
          value
        )}
      </div>
      {sublabel && !isLoading && !isError && <p className="text-xs text-muted-foreground">{sublabel}</p>}
    </div>
  )
}

export function PerformanceStatsRow({ stats, isLoading, isError }) {
  const delta = stats && stats.new_students_prev_7_days > 0 ? Math.round(((stats.new_students_last_7_days - stats.new_students_prev_7_days) / stats.new_students_prev_7_days) * 100) : null

  return (
    <div className="shadow-elevated grid overflow-hidden rounded-xl border sm:grid-cols-4">
      <MiniStat
        label="Avg. response time"
        value={formatDuration(stats?.avg_resolution_seconds)}
        isLoading={isLoading}
        isError={isError}
        sublabel={stats?.median_resolution_seconds != null ? `Median ${formatDuration(stats.median_resolution_seconds)}` : undefined}
      />
      <MiniStat
        label="Resolved (7d)"
        value={stats?.resolved_last_7_days ?? 0}
        isLoading={isLoading}
        isError={isError}
        sublabel={stats ? `${stats.resolved_today} today` : undefined}
      />
      <MiniStat
        label="New students (7d)"
        value={stats?.new_students_last_7_days ?? 0}
        isLoading={isLoading}
        isError={isError}
        sublabel={
          delta === null ? undefined : (
            <span className={cn("inline-flex items-center gap-0.5", delta >= 0 ? "text-hot-foreground dark:text-hot" : "text-muted-foreground")}>
              {delta >= 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
              {Math.abs(delta)}% vs prior 7d
            </span>
          )
        }
      />
      <MiniStat
        label="Bot self-serve rate"
        value={stats?.self_serve_rate_pct != null ? `${Math.round(stats.self_serve_rate_pct)}%` : "\u2014"}
        isLoading={isLoading}
        isError={isError}
        sublabel="Answered without escalation"
      />
    </div>
  )
}

// A hand-rolled bar sparkline (matching LeadScoreChart's reasoning for
// avoiding recharts) showing the trailing 7 days of message volume, plus
// the two numbers that give it context: how many conversations are live
// right now, and what share of them stall out almost immediately.
export function MessageActivityCard({ stats, isLoading, isError }) {
  const days = stats?.messages_last_7_days ?? []
  const maxCount = Math.max(1, ...days.map((d) => d.count))

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MessagesSquare className="size-4" />
          </span>
          <div>
            <CardTitle className="text-base">Message activity</CardTitle>
            <CardDescription>Volume over the last 7 days, plus who's talking right now.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <MetricBlockStatus isLoading={isLoading} isError={isError} isEmpty={!isLoading && !isError && days.every((d) => d.count === 0)} emptyMessage="No messages yet this week." />
        {!isLoading && !isError && days.some((d) => d.count > 0) && (
          // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
          <div className="flex h-[110px] items-end gap-2" role="img" aria-label="Bar chart of daily message volume over the last 7 days">
            {days.map((day) => (
              <div key={day.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
                <span className="text-[10px] text-muted-foreground">{day.count}</span>
                <div
                  className="w-full rounded-t-md bg-primary/70"
                  style={{ height: `${(day.count / maxCount) * 100}%`, minHeight: day.count > 0 ? "3px" : 0 }}
                />
                <span className="text-[10px] text-muted-foreground">
                  {new Date(day.date).toLocaleDateString(undefined, { weekday: "narrow" })}
                </span>
              </div>
            ))}
          </div>
        )}
        {!isLoading && !isError && (
          <div className="flex items-center gap-6 border-t pt-4 text-sm">
            <div>
              <p className="font-display text-lg font-semibold tracking-tight">{stats?.active_sessions ?? 0}</p>
              <p className="text-xs text-muted-foreground">Active sessions</p>
            </div>
            <div>
              <p className="font-display text-lg font-semibold tracking-tight">{stats?.bounce_rate_pct != null ? `${Math.round(stats.bounce_rate_pct)}%` : "\u2014"}</p>
              <p className="flex items-center gap-1 text-xs text-muted-foreground">
                <UserX className="size-3" /> Bounce rate
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Momentum on the lead pipeline itself: where new interest is landing
// (course_interest_breakdown) and two counts that flag where staff
// attention specifically needs to go - newly-hot leads and, more urgently,
// hot leads nobody currently owns.
export function LeadFunnelCard({ stats, isLoading, isError }) {
  const courses = stats?.course_interest_breakdown ?? []
  const maxCount = Math.max(1, ...courses.map((c) => c.count))

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary">
            <BookOpen className="size-4" />
          </span>
          <div>
            <CardTitle className="text-base">Lead funnel this week</CardTitle>
            <CardDescription>Where new interest is coming from and who needs a nudge.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <MetricBlockStatus isLoading={isLoading} isError={isError} />
        {!isLoading && !isError && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="hot" className="rounded-full">
                {stats.newly_hot_leads_last_7_days} newly hot (7d)
              </Badge>
              {stats.unassigned_hot_leads > 0 ? (
                <Link to="/students">
                  <Badge variant="destructive" className="rounded-full">
                    {stats.unassigned_hot_leads} hot &amp; unassigned
                  </Badge>
                </Link>
              ) : (
                <Badge variant="secondary" className="rounded-full">
                  All hot leads assigned
                </Badge>
              )}
            </div>
            {courses.length > 0 ? (
              <div className="flex flex-col gap-2">
                {courses.map((course) => (
                  <div key={course.course_interest} className="flex items-center gap-3">
                    <span className="w-28 shrink-0 truncate text-sm" title={course.course_interest}>
                      {course.course_interest}
                    </span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-primary/70" style={{ width: `${(course.count / maxCount) * 100}%` }} />
                    </div>
                    <span className="w-6 shrink-0 text-right text-xs text-muted-foreground">{course.count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No course interest recorded yet.</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

// Per-staff resolution counts over the trailing 7 days - who's actually
// clearing the queue, not just how big the queue is.
export function StaffLeaderboardCard({ stats, isLoading, isError }) {
  const staffRows = stats?.resolutions_by_staff_last_7_days ?? []
  const maxCount = Math.max(1, ...staffRows.map((s) => s.resolved_count))

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Trophy className="size-4" />
          </span>
          <div>
            <CardTitle className="text-base">Resolved by staff (7d)</CardTitle>
            <CardDescription>Who's been clearing the queue this week.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <MetricBlockStatus isLoading={isLoading} isError={isError} isEmpty={!isLoading && !isError && staffRows.length === 0} emptyMessage="No queries resolved by anyone this week yet." />
        {!isLoading && !isError && staffRows.length > 0 && (
          <div className="flex flex-col gap-2 pt-1">
            {staffRows.map((staff) => (
              <div key={staff.staff_id} className="flex items-center gap-3">
                <span className="w-28 shrink-0 truncate text-sm" title={staff.staff_name}>
                  {staff.staff_name}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary/70" style={{ width: `${(staff.resolved_count / maxCount) * 100}%` }} />
                </div>
                <span className="w-6 shrink-0 text-right text-xs text-muted-foreground">{staff.resolved_count}</span>
              </div>
            ))}
          </div>
        )}
        {!isLoading && !isError && (
          <div className="mt-3 border-t pt-3">
            <Link to="/queue" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
              View the full queue
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Upstream health of the RAG pipeline - a failed or low-quality document
// degrades every answer downstream of it, but there's otherwise no signal
// of that from Overview at all until a student notices a bad answer.
export function KnowledgeBaseHealthCard({ stats, isLoading, isError }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary">
            <FileWarning className="size-4" />
          </span>
          <div>
            <CardTitle className="text-base">Knowledge base health</CardTitle>
            <CardDescription>How well-fed the assistant's answers are right now.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <MetricBlockStatus isLoading={isLoading} isError={isError} />
        {!isLoading && !isError && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className={cn("font-display text-2xl font-semibold tracking-tight", stats.failed_documents > 0 && "text-destructive")}>{stats.failed_documents}</p>
              <p className="text-xs text-muted-foreground">Failed uploads</p>
            </div>
            <div>
              <p className="flex items-center gap-1 font-display text-2xl font-semibold tracking-tight">
                {stats.avg_document_quality_score != null ? stats.avg_document_quality_score.toFixed(2) : "\u2014"}
                <Star className="size-4 text-muted-foreground" />
              </p>
              <p className="text-xs text-muted-foreground">Avg. doc quality</p>
            </div>
            <div>
              <p className="font-display text-2xl font-semibold tracking-tight">{stats.staff_answers_added_last_7_days}</p>
              <p className="text-xs text-muted-foreground">New answers taught (7d)</p>
            </div>
            <div>
              <p className="font-display text-2xl font-semibold tracking-tight">{stats.oldest_open_query_age_seconds != null ? formatDuration(stats.oldest_open_query_age_seconds) : "\u2014"}</p>
              <p className="text-xs text-muted-foreground">Longest open wait</p>
            </div>
          </div>
        )}
        {!isLoading && !isError && stats.failed_documents > 0 && (
          <div className="mt-4 border-t pt-3">
            <Link to="/documents" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
              Review failed documents
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
