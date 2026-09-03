import { useMemo, useState } from "react"
import { Inbox } from "lucide-react"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { usePagination } from "@/hooks/usePagination"
import { ReplyToQueryDialog } from "@/components/ReplyToQueryDialog"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
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

export default function LowConfidenceQueue() {
  const { college, hasNoCollege } = useCurrentCollege()
  const [view, setView] = useState("open") // "open" | "resolved"
  const { data: queries, isLoading, isError, error } = useLowConfidenceQueries(college?.college_id, view === "resolved")
  const [activeQuery, setActiveQuery] = useState(null)

  const sortedQueries = useMemo(() => {
    if (!queries) return []
    // Oldest first for the open queue - that's what actually needs attention
    // soonest. For the resolved view, newest first reads more naturally as a
    // recent-activity log.
    return [...queries].sort((a, b) =>
      view === "open"
        ? new Date(a.flagged_at) - new Date(b.flagged_at)
        : new Date(b.resolved_at) - new Date(a.resolved_at)
    )
  }, [queries, view])

  const { page, setPage, totalPages, pageItems } = usePagination(sortedQueries, 15)

  if (hasNoCollege) {
    return (
      <EmptyState
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
        <p className="text-sm text-destructive">
          {error?.message || "Failed to load the queue. Please try again."}
        </p>
      )}

      {!isLoading && !isError && sortedQueries.length === 0 && (
        <EmptyState
          title={view === "open" ? "Nothing waiting on you" : "Nothing resolved yet"}
          description={
            view === "open"
              ? "Every flagged question has been resolved. New ones will show up here automatically."
              : "Resolved questions will show up here once you've replied to some."
          }
        />
      )}

      {(isLoading || pageItems.length > 0) && (
        <Table>
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
              pageItems.map((query) => (
                <TableRow key={query.query_id}>
                  <TableCell className="max-w-xs whitespace-normal">{query.question_content}</TableCell>
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

function EmptyState({ title, description }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
      <Inbox className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
