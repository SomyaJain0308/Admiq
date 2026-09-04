import { useState } from "react"
import { Inbox } from "lucide-react"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { ReplyToQueryDialog } from "@/components/ReplyToQueryDialog"
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
  const [page, setPage] = useState(1)
  const [activeQuery, setActiveQuery] = useState(null)

  // Switching between Open/Resolved is effectively a different list -
  // whatever page you were on in one view isn't meaningful in the other.
  const [prevView, setPrevView] = useState(view)
  if (view !== prevView) {
    setPrevView(view)
    setPage(1)
  }

  const { data, isLoading, isFetching, isError, error } = useLowConfidenceQueries(college?.college_id, view === "resolved", {
    page,
    pageSize: PAGE_SIZE,
  })

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
          <h1 className="text-2xl font-semibold">Low-confidence queue</h1>
          <p className="text-muted-foreground">
            Questions the assistant wasn't confident enough to answer on its own, for {college.college_name}.
          </p>
        </div>
        <div className="flex gap-1 rounded-md border bg-muted/30 p-1 shadow-[var(--shadow-xs)]">
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

      {(isLoading || queries.length > 0) && (
        <div className="overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-sm)]">
        <Table className={isFetching && !isLoading ? "opacity-60 transition-opacity" : undefined}>
          <TableHeader>
            <TableRow>
              <TableHead>Question</TableHead>
              <TableHead>Assistant's answer</TableHead>
              <TableHead className="w-24">{view === "open" ? "Waiting" : "Resolved"}</TableHead>
              <TableHead className="w-24"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={4} />
            ) : (
              queries.map((query) => (
                <TableRow key={query.query_id}>
                  <TableCell className="max-w-xs font-medium whitespace-normal">{query.question_content}</TableCell>
                  <TableCell className="max-w-xs whitespace-normal text-muted-foreground">
                    {query.answer_content}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {timeSince(view === "open" ? query.flagged_at : query.resolved_at)}
                  </TableCell>
                  <TableCell>
                    {view === "open" ? (
                      <Button size="sm" onClick={() => setActiveQuery(query)}>
                        Reply
                      </Button>
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
        onOpenChange={(open) => !open && setActiveQuery(null)}
      />
    </div>
  )
}

