import { useState } from "react"
import { toast } from "sonner"
import { ShieldAlert, ChevronDown, ChevronUp, FileText, MessageSquareText } from "lucide-react"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { useKnowledgeConflicts, useResolveConflict, useDismissConflict } from "@/hooks/useKnowledgeConflicts"
import { useResetPageOnChange } from "@/hooks/useResetPageOnChange"
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

const VIEWS = [
  { key: "open", label: "Open" },
  { key: "resolved", label: "Resolved" },
  { key: "dismissed", label: "Dismissed" },
]

export default function ConflictsQueue() {
  const { college, hasNoCollege } = useCurrentCollege()
  const [view, setView] = useState("open")
  const [page, setPage] = useResetPageOnChange(view)

  const { data, isLoading, isFetching, isError, error } = useKnowledgeConflicts(college?.college_id, view, {
    page,
    pageSize: PAGE_SIZE,
  })
  const resolveMutation = useResolveConflict(college?.college_id)
  const dismissMutation = useDismissConflict(college?.college_id)

  const conflicts = data?.items || []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  if (hasNoCollege) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="No college access yet"
        description="Your account isn't linked to a college yet. Contact an admin to get set up."
      />
    )
  }

  async function handleResolve(conflictId) {
    try {
      await resolveMutation.mutateAsync(conflictId)
      toast.success("Marked as resolved.")
    } catch (err) {
      toast.error(err?.message || "Failed to update the conflict. Please try again.")
    }
  }

  async function handleDismiss(conflictId) {
    try {
      await dismissMutation.mutateAsync(conflictId)
      toast.success("Dismissed - not a real conflict.")
    } catch (err) {
      toast.error(err?.message || "Failed to update the conflict. Please try again.")
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Conflicts</h1>
          <p className="text-muted-foreground">
            New documents and staff answers that seem to contradict something already in the knowledge base, for {college.college_name}.
          </p>
        </div>
        <div className="flex gap-1 rounded-md border bg-muted/30 p-1">
          {VIEWS.map(({ key, label }) => (
            <Button
              key={key}
              variant={view === key ? "default" : "ghost"}
              size="sm"
              onClick={() => setView(key)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load conflicts. Please try again."}
        </p>
      )}

      <p role="status" aria-live="polite" className="sr-only">
        {isFetching && !isLoading
          ? "Updating conflicts..."
          : !isLoading && !isError
            ? `${total} ${view} ${total === 1 ? "conflict" : "conflicts"}`
            : null}
      </p>

      {!isLoading && !isError && total === 0 && (
        <EmptyState
          icon={ShieldAlert}
          title={view === "open" ? "No open conflicts" : `Nothing ${view} yet`}
          description={
            view === "open"
              ? "Documents and staff answers are checked against the knowledge base automatically - anything that looks contradictory will show up here."
              : `Conflicts you've ${view === "resolved" ? "marked as resolved" : "dismissed"} will show up here.`
          }
        />
      )}

      {(isLoading || conflicts.length > 0) && (
        <div className="shadow-elevated overflow-hidden rounded-xl border">
          <Table className={isFetching && !isLoading ? "opacity-60 transition-opacity" : undefined}>
            <TableHeader>
              <TableRow>
                <TableHead className="w-64">New content</TableHead>
                <TableHead className="w-64">Conflicts with</TableHead>
                <TableHead>Why</TableHead>
                <TableHead className="w-24">{view === "open" ? "Flagged" : "Reviewed"}</TableHead>
                {view === "open" && <TableHead className="w-40"></TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableSkeletonRows columns={view === "open" ? 5 : 4} />
              ) : (
                conflicts.map((conflict) => (
                  <TableRow key={conflict.conflict_id}>
                    <TableCell className="max-w-xs align-top whitespace-normal">
                      <ChunkPreview chunk={conflict.new_chunk} />
                    </TableCell>
                    <TableCell className="max-w-xs align-top whitespace-normal">
                      <ChunkPreview chunk={conflict.existing_chunk} />
                    </TableCell>
                    <TableCell className="max-w-xs align-top whitespace-normal text-muted-foreground">
                      <ExpandableText text={conflict.explanation} />
                    </TableCell>
                    <TableCell className="align-top text-muted-foreground">
                      {timeSince(view === "open" ? conflict.created_at : conflict.resolved_at)}
                      {view !== "open" && conflict.resolved_by_name && (
                        <p className="text-xs">by {conflict.resolved_by_name}</p>
                      )}
                    </TableCell>
                    {view === "open" && (
                      <TableCell className="align-top">
                        <div className="flex flex-col gap-1.5">
                          <Button size="sm" onClick={() => handleResolve(conflict.conflict_id)} disabled={resolveMutation.isPending || dismissMutation.isPending}>
                            Mark resolved
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDismiss(conflict.conflict_id)}
                            disabled={resolveMutation.isPending || dismissMutation.isPending}
                          >
                            Not a conflict
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {!isLoading && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}
    </div>
  )
}

// One side of a flagged pair: where it came from (a document vs a staff
// answer) plus the actual text, so staff can judge the contradiction without
// having to go find either source separately.
function ChunkPreview({ chunk }) {
  const Icon = chunk.source_type === "document" ? FileText : MessageSquareText
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <Icon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate text-xs font-medium text-muted-foreground">{chunk.source_label}</span>
        {chunk.is_expired && (
          <Badge variant="secondary" className="shrink-0">
            Expired
          </Badge>
        )}
      </div>
      <ExpandableText text={chunk.content} />
    </div>
  )
}

// Same clamp-with-toggle pattern used on the low-confidence queue for long
// questions/answers - keeps a long chunk from blowing out the row height.
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
