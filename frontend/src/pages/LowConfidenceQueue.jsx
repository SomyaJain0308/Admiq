import { useMemo, useState } from "react"
import { Inbox, ChevronDown, ChevronUp, Users } from "lucide-react"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { useLowConfidenceQueries, useSimilarQueryGroups } from "@/hooks/useLowConfidenceQueue"
import { useResetPageOnChange } from "@/hooks/useResetPageOnChange"
import { ReplyToQueryDialog } from "@/components/ReplyToQueryDialog"
import { StudentSnapshot } from "@/components/StudentSnapshot"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { EmptyState } from "@/components/EmptyState"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { timeSince } from "@/lib/formatTime"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"

const PAGE_SIZE = 15

export default function LowConfidenceQueue() {
  const { college, hasNoCollege } = useCurrentCollege()
  const [view, setView] = useState("open") // "open" | "resolved"
  const [activeQuery, setActiveQuery] = useState(null)
  const [activeGroup, setActiveGroup] = useState(null)

  // Switching between Open/Resolved is effectively a different list -
  // whatever page you were on in one view isn't meaningful in the other.
  const [page, setPage] = useResetPageOnChange(view)

  const { data, isLoading, isFetching, isError, error } = useLowConfidenceQueries(college?.college_id, view === "resolved", {
    page,
    pageSize: PAGE_SIZE,
  })

  // Only meaningful for the open queue - resolved questions can't be
  // bundled into anything anymore.
  const { data: similarGroupsData } = useSimilarQueryGroups(college?.college_id, { enabled: view === "open" })
  const similarGroups = similarGroupsData?.groups || []

  // Quick lookup from a query_id to the group it belongs to (if any), so a
  // row anywhere on the current page can show its "N similar" badge without
  // re-scanning every group on every render.
  const groupByQueryId = useMemo(() => {
    const map = new Map()
    for (const group of similarGroups) {
      for (const queryId of group.query_ids) {
        map.set(queryId, group)
      }
    }
    return map
  }, [similarGroups])

  function openReply(query, group) {
    setActiveQuery(query)
    setActiveGroup(group || null)
  }

  const queries = data?.items || []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  if (hasNoCollege) {
    return (
      <EmptyState
        icon={Inbox}
        title="No college access yet"
        description="Your account isn't linked to a college yet. Contact an admin to get set up."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Low-confidence queue</h1>
          <p className="text-muted-foreground">
            Questions the assistant wasn't confident enough to answer on its own, for {college.college_name}.
          </p>
        </div>
        <div className="flex gap-1 rounded-md border bg-muted/30 p-1">
          <Button
            variant={view === "open" ? "default" : "ghost"}
            size="sm"
            onClick={() => setView("open")}
          >
            Open
          </Button>
          <Button
            variant={view === "resolved" ? "default" : "ghost"}
            size="sm"
            onClick={() => setView("resolved")}
          >
            Resolved
          </Button>
        </div>
      </div>

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load the queue. Please try again."}
        </p>
      )}

      {/* Visually hidden - the table itself already shows this via the dim/
          opacity transition, but that's a purely visual cue. This gives
          screen-reader users the same "list just updated" signal. */}
      <p role="status" aria-live="polite" className="sr-only">
        {isFetching && !isLoading
          ? "Updating queue..."
          : !isLoading && !isError
            ? `${total} ${view === "open" ? "open" : "resolved"} ${total === 1 ? "query" : "queries"}`
            : null}
      </p>

      {!isLoading && !isError && total === 0 && (
        <EmptyState
          icon={Inbox}
          title={view === "open" ? "Nothing waiting on you" : "Nothing resolved yet"}
          description={
            view === "open"
              ? "Every flagged question has been resolved. New ones will show up here automatically."
              : "Resolved questions will show up here once you've replied to some."
          }
        />
      )}

      {view === "open" && similarGroups.length > 0 && (
        <div className="flex flex-col gap-2 rounded-xl border border-primary/30 bg-primary/5 p-4">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <Users className="size-4" />
            {similarGroups.length} group{similarGroups.length === 1 ? "" : "s"} of students asking basically the same thing
          </p>
          <p className="text-xs text-muted-foreground">
            Reply once and it goes out to everyone in the group, instead of answering the same question repeatedly.
          </p>
          <div className="flex flex-col gap-2">
            {similarGroups.map((group) => {
              const representative = group.members[0]
              return (
                <div
                  key={group.query_ids.join("-")}
                  className="flex flex-col gap-2 rounded-md border bg-background p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-medium">{representative.question_content}</span>
                    <span className="text-xs text-muted-foreground">
                      {group.members.length} students asked a version of this question
                    </span>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => openReply(representative, group.members)}>
                    Reply to all {group.members.length}
                  </Button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {(isLoading || queries.length > 0) && (
        <div className="shadow-elevated overflow-hidden rounded-xl border">
        <Table className={isFetching && !isLoading ? "opacity-60 transition-opacity" : undefined}>
          <TableHeader>
            <TableRow>
              <TableHead className="w-48">Student</TableHead>
              <TableHead>Question</TableHead>
              <TableHead>Assistant's answer</TableHead>
              <TableHead className="w-24">{view === "open" ? "Waiting" : "Resolved"}</TableHead>
              <TableHead className="w-24"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={5} />
            ) : (
              queries.map((query) => (
                <TableRow key={query.query_id}>
                  <TableCell>
                    <StudentSnapshot collegeId={college?.college_id} studentId={query.student_id} />
                  </TableCell>
                  <TableCell className="max-w-xs font-medium whitespace-normal">
                    <ExpandableText text={query.question_content} />
                  </TableCell>
                  <TableCell className="max-w-xs whitespace-normal text-muted-foreground">
                    <ExpandableText text={query.answer_content} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {timeSince(view === "open" ? query.flagged_at : query.resolved_at)}
                  </TableCell>
                  <TableCell>
                    {view === "open" ? (
                      <div className="flex flex-col items-start gap-1">
                        <Button size="sm" onClick={() => openReply(query, groupByQueryId.get(query.query_id)?.members)}>
                          Reply
                        </Button>
                        {groupByQueryId.has(query.query_id) && (
                          <Badge variant="outline" className="text-[10px]">
                            +{groupByQueryId.get(query.query_id).members.length - 1} similar
                          </Badge>
                        )}
                      </div>
                    ) : (
                      <Badge variant="secondary">Resolved</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        </div>
      )}

      {!isLoading && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}

      <ReplyToQueryDialog
        query={activeQuery}
        collegeId={college?.college_id}
        open={!!activeQuery}
        onOpenChange={(open) => {
          if (!open) {
            setActiveQuery(null)
            setActiveGroup(null)
          }
        }}
        similarGroup={activeGroup}
      />
    </div>
  )
}

// Long questions/answers used to just push the row as tall as the text
// needed - fine for a sentence, but a long assistant answer could make a
// single row take up half the screen. Clamp to 3 lines with a toggle,
// same "Show more" pattern already used for document errors elsewhere.
function ExpandableText({ text }) {
  const [expanded, setExpanded] = useState(false)

  if (!text) return null

  return (
    <div>
      <p className={expanded ? undefined : "line-clamp-3"}>{text}</p>
      {text.length > 160 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-0.5 inline-flex items-center gap-0.5 text-xs font-medium text-foreground underline underline-offset-2"
        >
          {expanded ? (
            <>
              Show less <ChevronUp className="size-3" />
            </>
          ) : (
            <>
              Show more <ChevronDown className="size-3" />
            </>
          )}
        </button>
      )}
    </div>
  )
}
