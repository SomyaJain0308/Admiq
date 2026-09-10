import { useMemo, useRef, useState } from "react"
import { FileText, Loader2, CheckCircle2, XCircle, Upload, Trash2, Eye, RotateCw, ChevronDown, ChevronUp, Search, X } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import {
  useDocuments,
  useUploadDocument,
  useDeleteDocument,
  useBulkDeleteDocuments,
  useViewDocument,
  useRetryDocument,
} from "@/hooks/useDocuments"
import { usePagination } from "@/hooks/usePagination"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { EmptyState, FilteredEmptyState } from "@/components/EmptyState"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { cn } from "@/lib/utils"
import { timeSince } from "@/lib/formatTime"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"

const MAX_FILE_SIZE_MB = 25
const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "processing", label: "Processing" },
  { value: "success", label: "Success" },
  { value: "failed", label: "Failed" },
]

let uploadIdCounter = 0

export default function DocumentsPage() {
  const { college, hasNoCollege } = useCurrentCollege()
  const { data: documents, isLoading, isError, error } = useDocuments(college?.college_id)
  const uploadMutation = useUploadDocument(college?.college_id)
  const deleteMutation = useDeleteDocument(college?.college_id)
  const bulkDeleteMutation = useBulkDeleteDocuments(college?.college_id)
  const viewMutation = useViewDocument(college?.college_id)
  const retryMutation = useRetryDocument(college?.college_id)
  const fileInputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)

  // Per-file upload progress. Files upload in parallel (rather than one at a
  // time) so each gets its own live status instead of a single shared
  // "Uploading..." spinner that gives no sense of which file is done.
  const [uploads, setUploads] = useState([])

  const [searchInput, setSearchInput] = useState("")
  const debouncedSearch = useDebouncedValue(searchInput, 250)
  const [statusFilter, setStatusFilter] = useState("all")
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [confirmDeleteDoc, setConfirmDeleteDoc] = useState(null)
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false)

  const filteredDocuments = useMemo(() => {
    let list = documents || []
    if (statusFilter !== "all") {
      list = list.filter((d) => d.status === statusFilter)
    }
    const q = debouncedSearch.trim().toLowerCase()
    if (q) {
      list = list.filter((d) => d.file_name.toLowerCase().includes(q))
    }
    return list
  }, [documents, statusFilter, debouncedSearch])

  const { page, setPage, totalPages, pageItems } = usePagination(filteredDocuments, 15)

  const activeUploads = uploads.filter((u) => u.status === "uploading")
  const pageIds = pageItems.map((d) => d.document_id)
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id))
  const someOnPageSelected = pageIds.some((id) => selectedIds.has(id))

  function toggleSelected(documentId) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(documentId)) next.delete(documentId)
      else next.add(documentId)
      return next
    })
  }

  function toggleSelectAllOnPage() {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (allOnPageSelected) {
        pageIds.forEach((id) => next.delete(id))
      } else {
        pageIds.forEach((id) => next.add(id))
      }
      return next
    })
  }

  async function handleView(doc) {
    try {
      await viewMutation.mutateAsync(doc.document_id)
    } catch (err) {
      toast.error(err?.message || `Failed to open ${doc.file_name}.`)
    }
  }

  function requestDelete(doc) {
    setConfirmDeleteDoc(doc)
  }

  async function confirmSingleDelete() {
    const doc = confirmDeleteDoc
    if (!doc) return
    setConfirmDeleteDoc(null)
    try {
      await deleteMutation.mutateAsync(doc.document_id)
      toast.success(`${doc.file_name} deleted.`)
    } catch (err) {
      toast.error(err?.message || "Failed to delete document.")
    }
  }

  async function confirmBulkDeleteAction() {
    const ids = Array.from(selectedIds)
    setConfirmBulkDelete(false)
    try {
      const result = await bulkDeleteMutation.mutateAsync(ids)
      setSelectedIds(new Set())
      if (result.failedIds.length > 0) {
        toast.error(`${result.succeededCount} deleted, ${result.failedIds.length} failed. Try those again.`)
      } else {
        toast.success(`${result.succeededCount} document${result.succeededCount === 1 ? "" : "s"} deleted.`)
      }
    } catch (err) {
      toast.error(err?.message || "Failed to delete selected documents.")
    }
  }

  async function handleRetry(doc) {
    try {
      await retryMutation.mutateAsync(doc.document_id)
      toast.success(`Retrying ${doc.file_name}.`)
    } catch (err) {
      toast.error(err?.message || `Failed to retry ${doc.file_name}.`)
    }
  }

  function updateUpload(id, patch) {
    setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)))
  }

  async function handleFiles(fileList) {
    const files = Array.from(fileList || [])
    const toUpload = []

    for (const file of files) {
      if (file.type !== "application/pdf") {
        toast.error(`${file.name} isn't a PDF - only PDF files are supported right now.`)
        continue
      }
      if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        toast.error(`${file.name} is too large - max ${MAX_FILE_SIZE_MB}MB at a time.`)
        continue
      }
      toUpload.push({ id: ++uploadIdCounter, file, name: file.name, status: "uploading" })
    }

    if (toUpload.length === 0) return

    setUploads((prev) => [...prev, ...toUpload.map(({ id, name, status }) => ({ id, name, status }))])

    // Fire all uploads in parallel so a batch of files each gets its own
    // live status instead of the UI looking frozen while file 1 of 5 sits
    // in a sequential await chain.
    await Promise.allSettled(
      toUpload.map(async ({ id, file, name }) => {
        try {
          await uploadMutation.mutateAsync(file)
          updateUpload(id, { status: "done" })
          toast.success(`${name} uploaded - processing now.`)
        } catch (err) {
          updateUpload(id, { status: "error", errorMessage: err?.message })
          toast.error(err?.message || `Failed to upload ${name}. Please try again.`)
        } finally {
          // Clear this file's row out of the progress list a moment after
          // it settles, so short uploads don't leave stale "Done" entries
          // sitting around, but the person still gets to see it land.
          setTimeout(() => {
            setUploads((prev) => prev.filter((u) => u.id !== id))
          }, 2500)
        }
      })
    )
  }

  function onDrop(e) {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="text-muted-foreground">
          Upload PDFs for {college.college_name} - the assistant answers student questions from these.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed py-10 text-center transition-colors",
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25"
        )}
      >
        <Upload className="size-8 text-muted-foreground" />
        <div>
          <p className="font-medium">Drag and drop PDFs here</p>
          <p className="text-sm text-muted-foreground">or click below to browse - max {MAX_FILE_SIZE_MB}MB per file</p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files)
            e.target.value = ""
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={activeUploads.length > 0}
          onClick={() => fileInputRef.current?.click()}
        >
          {activeUploads.length > 0 ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Uploading...
            </>
          ) : (
            "Choose files"
          )}
        </Button>
      </div>

      {uploads.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-lg border bg-muted/30 p-3">
          <p className="text-xs font-medium text-muted-foreground">
            {activeUploads.length > 0
              ? // Files upload in parallel, not one at a time - "X of Y done"
                // reads accurately no matter how many are still in flight at
                // once, unlike a "Uploading X of Y..." framing that implies
                // a sequential queue.
                `${uploads.length - activeUploads.length} of ${uploads.length} uploaded...`
              : "Upload finished"}
          </p>
          {uploads.map((u) => (
            <div key={u.id} className="flex items-center gap-2 text-sm">
              {u.status === "uploading" && <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />}
              {u.status === "done" && <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600" />}
              {u.status === "error" && <XCircle className="size-3.5 shrink-0 text-destructive" />}
              <span className="truncate">{u.name}</span>
            </div>
          ))}
        </div>
      )}

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load documents. Please try again."}
        </p>
      )}

      {!isLoading && !isError && documents?.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No documents yet"
          description="Upload a PDF above to get started - the assistant will use it to answer student questions."
        />
      )}

      {!isLoading && !isError && documents?.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(e) => {
                  setSearchInput(e.target.value)
                  setPage(1)
                }}
                placeholder="Search by filename..."
                className="pl-8"
                aria-label="Search documents by filename"
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
              {STATUS_FILTERS.map((f) => (
                <Button
                  key={f.value}
                  type="button"
                  size="sm"
                  variant={statusFilter === f.value ? "secondary" : "ghost"}
                  onClick={() => {
                    setStatusFilter(f.value)
                    setPage(1)
                  }}
                >
                  {f.label}
                </Button>
              ))}
            </div>
          </div>

          {selectedIds.size > 0 && (
            <div className="flex items-center justify-between rounded-md border bg-muted/40 px-3 py-2">
              <p className="text-sm font-medium">{selectedIds.size} selected</p>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
                  Clear
                </Button>
                <Button type="button" size="sm" variant="destructive" onClick={() => setConfirmBulkDelete(true)}>
                  <Trash2 className="size-4" />
                  Delete selected
                </Button>
              </div>
            </div>
          )}

          {filteredDocuments.length === 0 ? (
            <FilteredEmptyState
              message={
                debouncedSearch && statusFilter !== "all"
                  ? `No ${statusFilter} documents match "${debouncedSearch}".`
                  : debouncedSearch
                    ? `No documents match "${debouncedSearch}".`
                    : `No ${statusFilter} documents.`
              }
              clearLabel="Clear filters"
              onClear={() => {
                setSearchInput("")
                setStatusFilter("all")
              }}
            />
          ) : (
            <div className="shadow-elevated overflow-hidden rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={allOnPageSelected ? true : someOnPageSelected ? "indeterminate" : false}
                      onCheckedChange={toggleSelectAllOnPage}
                      aria-label="Select all documents on this page"
                    />
                  </TableHead>
                  <TableHead>File</TableHead>
                  <TableHead className="w-28">Status</TableHead>
                  <TableHead className="w-20">Pages</TableHead>
                  <TableHead className="w-24">Uploaded</TableHead>
                  <TableHead className="w-28"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageItems.map((doc) => (
                  <DocumentRow
                    key={doc.document_id}
                    doc={doc}
                    isSelected={selectedIds.has(doc.document_id)}
                    onToggleSelected={() => toggleSelected(doc.document_id)}
                    onDelete={requestDelete}
                    isDeleting={deleteMutation.isPending && deleteMutation.variables === doc.document_id}
                    onView={handleView}
                    isViewing={viewMutation.isPending && viewMutation.variables === doc.document_id}
                    onRetry={handleRetry}
                    isRetrying={retryMutation.isPending && retryMutation.variables === doc.document_id}
                  />
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </div>
      )}

      {isLoading && (
        <div className="shadow-elevated overflow-hidden rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10"></TableHead>
              <TableHead>File</TableHead>
              <TableHead className="w-28">Status</TableHead>
              <TableHead className="w-20">Pages</TableHead>
              <TableHead className="w-24">Uploaded</TableHead>
              <TableHead className="w-28"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableSkeletonRows columns={6} />
          </TableBody>
        </Table>
        </div>
      )}

      {!isLoading && documents?.length > 0 && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}

      <ConfirmDialog
        open={!!confirmDeleteDoc}
        onOpenChange={(open) => !open && setConfirmDeleteDoc(null)}
        title={`Delete "${confirmDeleteDoc?.file_name}"?`}
        description="The assistant will stop using it to answer questions - this can't be undone."
        onConfirm={confirmSingleDelete}
        isConfirming={deleteMutation.isPending}
      />

      <ConfirmDialog
        open={confirmBulkDelete}
        onOpenChange={setConfirmBulkDelete}
        title={`Delete ${selectedIds.size} document${selectedIds.size === 1 ? "" : "s"}?`}
        description={`The assistant will stop using ${selectedIds.size === 1 ? "it" : "them"} to answer questions - this can't be undone.`}
        onConfirm={confirmBulkDeleteAction}
        isConfirming={bulkDeleteMutation.isPending}
      />
    </div>
  )
}

function DocumentRow({ doc, isSelected, onToggleSelected, onDelete, isDeleting, onView, isViewing, onRetry, isRetrying }) {
  const [errorExpanded, setErrorExpanded] = useState(false)
  const hasDiagnostics = doc.quality_score != null || doc.extraction_method
  const errorIsLong = (doc.error?.length || 0) > 90
  const displayedError = !doc.error ? null : errorExpanded || !errorIsLong ? doc.error : `${doc.error.slice(0, 90)}...`

  return (
    <TableRow className={isDeleting ? "opacity-50" : undefined}>
      <TableCell>
        <Checkbox checked={isSelected} onCheckedChange={onToggleSelected} aria-label={`Select ${doc.file_name}`} />
      </TableCell>
      <TableCell className="max-w-xs">
        <button
          type="button"
          onClick={() => onView(doc)}
          disabled={isViewing}
          className="block truncate text-left font-medium hover:underline disabled:cursor-wait disabled:no-underline disabled:opacity-70"
          title={`Open ${doc.file_name}`}
        >
          {doc.file_name}
        </button>
        {doc.status === "failed" && doc.error && (
          <p className="mt-0.5 text-xs text-destructive">
            {displayedError}
            {errorIsLong && (
              <button
                type="button"
                onClick={() => setErrorExpanded((v) => !v)}
                className="ml-1 inline-flex items-center gap-0.5 font-medium underline underline-offset-2"
              >
                {errorExpanded ? (
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
          </p>
        )}
        {hasDiagnostics && (
          <p className="mt-0.5 text-xs text-muted-foreground">
            {doc.extraction_method && <span>Extracted via {doc.extraction_method}</span>}
            {doc.extraction_method && doc.quality_score != null && <span> · </span>}
            {doc.quality_score != null && <span>Quality {doc.quality_score.toFixed(2)}</span>}
          </p>
        )}
      </TableCell>
      <TableCell>
        <StatusBadge status={doc.status} />
      </TableCell>
      <TableCell className="text-muted-foreground">{doc.num_pages ?? "-"}</TableCell>
      <TableCell className="text-muted-foreground">{timeSince(doc.created_at)}</TableCell>
      <TableCell>
        <div className="flex items-center">
          {doc.status === "failed" && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Retry processing ${doc.file_name}`}
              disabled={isRetrying}
              onClick={() => onRetry(doc)}
            >
              {isRetrying ? <Loader2 className="size-4 animate-spin" /> : <RotateCw className="size-4 text-muted-foreground" />}
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`View ${doc.file_name}`}
            disabled={isViewing}
            onClick={() => onView(doc)}
          >
            {isViewing ? <Loader2 className="size-4 animate-spin" /> : <Eye className="size-4 text-muted-foreground" />}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Delete ${doc.file_name}`}
            disabled={isDeleting}
            onClick={() => onDelete(doc)}
          >
            {isDeleting ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4 text-muted-foreground" />}
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

function StatusBadge({ status }) {
  if (status === "success") {
    return (
      <Badge variant="secondary" className="gap-1">
        <CheckCircle2 className="size-3" />
        Success
      </Badge>
    )
  }
  if (status === "failed") {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="size-3" />
        Failed
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="gap-1">
      <Loader2 className="size-3 animate-spin" />
      Processing
    </Badge>
  )
}
