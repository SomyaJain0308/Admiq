import { useState } from "react"
import { BookOpen, Plus, Pencil, Trash2, Search, X, Clock, TrendingUp } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { useKnowledgeBase, useDeleteKnowledgeBaseEntry } from "@/hooks/useKnowledgeBase"
import { useResetPageOnChange } from "@/hooks/useResetPageOnChange"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { KnowledgeBaseEntryDialog } from "@/components/KnowledgeBaseEntryDialog"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { EmptyState, FilteredEmptyState } from "@/components/EmptyState"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
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
const FILTERS = [
  { value: "all", label: "All" },
  { value: "expiring_soon", label: "Expiring soon" },
  { value: "unused", label: "Rarely used" },
]

export default function KnowledgeBasePage() {
  const { college, hasNoCollege } = useCurrentCollege()
  const [searchInput, setSearchInput] = useState("")
  const debouncedSearch = useDebouncedValue(searchInput, 300)
  const [filter, setFilter] = useState("all")
  const [page, setPage] = useResetPageOnChange(`${debouncedSearch}|${filter}`)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingEntry, setEditingEntry] = useState(null)
  const [confirmDeleteEntry, setConfirmDeleteEntry] = useState(null)

  const { data, isLoading, isError, error } = useKnowledgeBase(college?.college_id, {
    search: debouncedSearch,
    expiringSoon: filter === "expiring_soon",
    unused: filter === "unused",
    page,
    pageSize: PAGE_SIZE,
  })
  const deleteMutation = useDeleteKnowledgeBaseEntry(college?.college_id)

  const entries = data?.items || []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hasActiveFilter = !!debouncedSearch || filter !== "all"

  function openAddDialog() {
    setEditingEntry(null)
    setDialogOpen(true)
  }

  function openEditDialog(entry) {
    setEditingEntry(entry)
    setDialogOpen(true)
  }

  async function confirmDelete() {
    const entry = confirmDeleteEntry
    if (!entry) return
    setConfirmDeleteEntry(null)
    try {
      await deleteMutation.mutateAsync(entry.chunk_id)
      toast.success("Entry deleted.")
    } catch (err) {
      toast.error(err?.message || "Failed to delete entry.")
    }
  }

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Knowledge base</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Knowledge base</h1>
          <p className="text-muted-foreground">
            Every staff answer the assistant can draw on for {college.college_name} - search, edit, or retire any of them.
          </p>
        </div>
        <Button type="button" onClick={openAddDialog} className="gap-1.5">
          <Plus className="size-4" />
          Add Q&A
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search questions and answers..."
            className="pl-8"
            aria-label="Search the knowledge base"
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => setSearchInput("")}
              className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <Button
              key={f.value}
              type="button"
              size="sm"
              variant={filter === f.value ? "secondary" : "ghost"}
              onClick={() => setFilter(f.value)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load the knowledge base. Please try again."}
        </p>
      )}

      {!isLoading && !isError && entries.length === 0 && !hasActiveFilter && (
        <EmptyState
          icon={BookOpen}
          title="No staff answers yet"
          description={'Once a low-confidence question is resolved it lands here - or add one proactively with "Add Q&A" above.'}
          action={{ label: "Add Q&A", onClick: openAddDialog }}
        />
      )}

      {!isLoading && !isError && entries.length === 0 && hasActiveFilter && (
        <FilteredEmptyState
          message={
            debouncedSearch
              ? `No entries match "${debouncedSearch}".`
              : filter === "expiring_soon"
                ? "Nothing is expiring soon."
                : "Nothing looks rarely-used right now."
          }
          clearLabel="Clear filters"
          onClear={() => {
            setSearchInput("")
            setFilter("all")
          }}
        />
      )}

      {!isLoading && !isError && entries.length > 0 && (
        <div className="shadow-elevated overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question &amp; answer</TableHead>
                <TableHead className="w-24">Origin</TableHead>
                <TableHead className="w-28">Usage</TableHead>
                <TableHead className="w-28">Expiry</TableHead>
                <TableHead className="w-28">Added</TableHead>
                <TableHead className="w-20"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <EntryRow
                  key={entry.chunk_id}
                  entry={entry}
                  onEdit={openEditDialog}
                  onDelete={setConfirmDeleteEntry}
                  isDeleting={deleteMutation.isPending && deleteMutation.variables === entry.chunk_id}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {isLoading && (
        <div className="shadow-elevated overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question &amp; answer</TableHead>
                <TableHead className="w-24">Origin</TableHead>
                <TableHead className="w-28">Usage</TableHead>
                <TableHead className="w-28">Expiry</TableHead>
                <TableHead className="w-28">Added</TableHead>
                <TableHead className="w-20"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableSkeletonRows columns={6} />
            </TableBody>
          </Table>
        </div>
      )}

      {!isLoading && entries.length > 0 && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}

      <KnowledgeBaseEntryDialog collegeId={college?.college_id} open={dialogOpen} onOpenChange={setDialogOpen} editingEntry={editingEntry} />

      <ConfirmDialog
        open={!!confirmDeleteEntry}
        onOpenChange={(open) => !open && setConfirmDeleteEntry(null)}
        title="Delete this entry?"
        description="The assistant will stop using it to answer students - this can't be undone."
        onConfirm={confirmDelete}
        isConfirming={deleteMutation.isPending}
      />
    </div>
  )
}

function EntryRow({ entry, onEdit, onDelete, isDeleting }) {
  return (
    <TableRow className={isDeleting ? "opacity-50" : undefined}>
      <TableCell className="max-w-md align-top">
        <p className="font-medium">{entry.question || "(no question text)"}</p>
        <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{entry.answer}</p>
      </TableCell>
      <TableCell className="align-top">
        {entry.origin === "proactive" ? (
          <Badge variant="outline">Proactive</Badge>
        ) : (
          <Badge variant="secondary">Reactive</Badge>
        )}
      </TableCell>
      <TableCell className="align-top">
        <div className="flex items-center gap-1 text-sm">
          <TrendingUp className="size-3.5 text-muted-foreground" />
          <span>{entry.retrieval_count}x</span>
        </div>
        {entry.last_retrieved_at && (
          <p className="mt-0.5 text-xs text-muted-foreground">last used {timeSince(entry.last_retrieved_at)} ago</p>
        )}
      </TableCell>
      <TableCell className="align-top">
        {entry.expires_at ? (
          <Badge variant={entry.is_expired ? "destructive" : "outline"} className="gap-1">
            <Clock className="size-3" />
            {entry.is_expired ? "Expired" : new Date(entry.expires_at).toLocaleDateString()}
          </Badge>
        ) : (
          <span className="text-sm text-muted-foreground">Never</span>
        )}
      </TableCell>
      <TableCell className="align-top text-muted-foreground">
        {entry.created_at && <p>{timeSince(entry.created_at)}</p>}
        {entry.created_by_name && <p className="text-xs">by {entry.created_by_name}</p>}
      </TableCell>
      <TableCell className="align-top">
        <div className="flex items-center">
          <Button type="button" variant="ghost" size="icon" aria-label="Edit entry" onClick={() => onEdit(entry)}>
            <Pencil className="size-4 text-muted-foreground" />
          </Button>
          <Button type="button" variant="ghost" size="icon" aria-label="Delete entry" disabled={isDeleting} onClick={() => onDelete(entry)}>
            <Trash2 className="size-4 text-muted-foreground" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
