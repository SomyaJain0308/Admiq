import { useMemo, useRef, useState } from "react"
import {
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  Upload,
  Trash2,
  Eye,
  RotateCw,
  ChevronDown,
  ChevronUp,
  Search,
  X,
  FileSearch,
  FileUp,
} from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { ApiError } from "@/lib/api"
import {
  useDocuments,
  useUploadDocument,
  useReplaceDocument,
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
import { DocumentPreviewDialog } from "@/components/DocumentPreviewDialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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

// Mirrors backend ALLOWED_CONTENT_TYPES in routers/documents.py.
const ALLOWED_FILE_TYPES = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word (.docx)",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel (.xlsx)",
}
const ACCEPT_ATTR = ".pdf,.docx,.xlsx," + Object.keys(ALLOWED_FILE_TYPES).join(",")

// A starter set of topic labels - purely organizational (filtering/browsing
// the documents list), doesn't affect retrieval. Staff can leave it unset.
const CATEGORIES = ["Admissions", "Fees", "Hostel & Facilities", "Courses & Programs", "Scholarships", "General"]
const SELECT_CLASSES =
  "border-input h-9 rounded-md border bg-transparent px-2.5 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"

let uploadIdCounter = 0

export default function DocumentsPage() {
  const { college, hasNoCollege } = useCurrentCollege()
  const { data: documents, isLoading, isError, error } = useDocuments(college?.college_id)
  const uploadMutation = useUploadDocument(college?.college_id)
  const replaceMutation = useReplaceDocument(college?.college_id)
  const deleteMutation = useDeleteDocument(college?.college_id)
  const bulkDeleteMutation = useBulkDeleteDocuments(college?.college_id)
  const viewMutation = useViewDocument(college?.college_id)
  const retryMutation = useRetryDocument(college?.college_id)
  const fileInputRef = useRef(null)
  const replaceInputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)

  // Per-file upload progress. Files upload in parallel (rather than one at a
  // time) so each gets its own live status instead of a single shared
  // "Uploading..." spinner that gives no sense of which file is done.
  const [uploads, setUploads] = useState([])
  const [uploadCategory, setUploadCategory] = useState("")

  const [searchInput, setSearchInput] = useState("")
  const debouncedSearch = useDebouncedValue(searchInput, 250)
  const [statusFilter, setStatusFilter] = useState("all")
  const [categoryFilter, setCategoryFilter] = useState("all")
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [confirmDeleteDoc, setConfirmDeleteDoc] = useState(null)
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false)
  const [previewDoc, setPreviewDoc] = useState(null)
  const [replaceTargetDoc, setReplaceTargetDoc] = useState(null)

  // Every category currently in use, for the filter dropdown - derived from
  // the data rather than hardcoded, so a category typed in once (or added
  // to CATEGORIES later) shows up automatically.
  const usedCategories = useMemo(
    () => Array.from(new Set((documents || []).map((d) => d.category).filter(Boolean))).sort(),
    [documents]
  )

  const filteredDocuments = useMemo(() => {
    let list = documents || []
    if (statusFilter !== "all") {
      list = list.filter((d) => d.status === statusFilter)
    }
    if (categoryFilter === "__uncategorized") {
      list = list.filter((d) => !d.category)
    } else if (categoryFilter !== "all") {
      list = list.filter((d) => d.category === categoryFilter)
    }
    const q = debouncedSearch.trim().toLowerCase()
    if (q) {
      list = list.filter((d) => d.file_name.toLowerCase().includes(q))
    }
    return list
  }, [documents, statusFilter, categoryFilter, debouncedSearch])

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

  // One file's upload attempt. Broken out from handleFiles so a duplicate
  // warning's "Upload anyway" action can re-run the exact same attempt with
  // force=true, instead of duplicating the upload/toast logic.
  async function attemptUpload(id, file, name, force) {
    try {
      await uploadMutation.mutateAsync({ file, category: uploadCategory || null, force })
      updateUpload(id, { status: "done" })
      toast.success(`${name} uploaded - processing now.`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        updateUpload(id, { status: "error", errorMessage: "Possible duplicate" })
        toast.warning(err.message || `${name} looks like a duplicate.`, {
          duration: 15000,
          action: { label: "Upload anyway", onClick: () => attemptUpload(id, file, name, true) },
        })
        return
      }
      updateUpload(id, { status: "error", errorMessage: err?.message })
      toast.error(err?.message || `Failed to upload ${name}. Please try again.`)
    }
  }

  async function handleFiles(fileList) {
    const files = Array.from(fileList || [])
    const toUpload = []

    for (const file of files) {
      if (!ALLOWED_FILE_TYPES[file.type]) {
        toast.error(`${file.name} isn't a supported file type - PDF, Word (.docx), or Excel (.xlsx) only.`)
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
        await attemptUpload(id, file, name, false)
        // Clear this file's row out of the progress list a moment after it
        // settles, so short uploads don't leave stale "Done" entries sitting
        // around, but the person still gets to see it land. A later "Upload
        // anyway" click (from the duplicate toast) still goes through even
        // after this row is gone - it just won't have a progress row of
        // its own, which is fine since the toast itself covers that.
        setTimeout(() => {
          setUploads((prev) => prev.filter((u) => u.id !== id))
        }, 2500)
      })
    )
  }

  function onDrop(e) {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  function requestReplace(doc) {
    setReplaceTargetDoc(doc)
    // The hidden input is shared across every row - wait a tick so its
    // onChange handler below can see the freshly-set target before the
    // native file picker's change event fires.
    requestAnimationFrame(() => replaceInputRef.current?.click())
  }

  async function handleReplaceFileSelected(e) {
    const file = e.target.files?.[0]
    e.target.value = ""
    const doc = replaceTargetDoc
    setReplaceTargetDoc(null)
    if (!file || !doc) return
    if (!ALLOWED_FILE_TYPES[file.type]) {
      toast.error(`${file.name} isn't a supported file type - PDF, Word (.docx), or Excel (.xlsx) only.`)
      return
    }
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      toast.error(`${file.name} is too large - max ${MAX_FILE_SIZE_MB}MB at a time.`)
      return
    }
    try {
      await replaceMutation.mutateAsync({ documentId: doc.document_id, file, category: doc.category })
      toast.success(`${doc.file_name} replaced with ${file.name} - reprocessing now.`)
    } catch (err) {
      toast.error(err?.message || `Failed to replace ${doc.file_name}.`)
    }
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
          Upload files for {college.college_name} - the assistant answers student questions from these.
        </p>
      </div>

      <div className="flex flex-col gap-1.5 self-start">
        <Label htmlFor="upload-category" className="text-xs font-medium text-muted-foreground">
          Category for this batch (optional)
        </Label>
        <select
          id="upload-category"
          value={uploadCategory}
          onChange={(e) => setUploadCategory(e.target.value)}
          className={cn(SELECT_CLASSES, "w-56")}
        >
          <option value="">Uncategorized</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
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
          <p className="font-medium">Drag and drop files here</p>
          <p className="text-sm text-muted-foreground">
            PDF, Word, or Excel - or click below to browse - max {MAX_FILE_SIZE_MB}MB per file
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files)
            e.target.value = ""
          }}
        />
        {/* Shared across every row's "Replace" action - which document it targets
            is tracked in replaceTargetDoc rather than one input per row. */}
        <input ref={replaceInputRef} type="file" accept={ACCEPT_ATTR} className="hidden" onChange={handleReplaceFileSelected} />
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
            <div className="flex flex-wrap items-center gap-1.5">
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
              {usedCategories.length > 0 && (
                <select
                  aria-label="Filter by category"
                  value={categoryFilter}
                  onChange={(e) => {
                    setCategoryFilter(e.target.value)
                    setPage(1)
                  }}
                  className={cn(SELECT_CLASSES, "w-40")}
                >
                  <option value="all">All categories</option>
                  {usedCategories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                  <option value="__uncategorized">Uncategorized</option>
                </select>
              )}
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
                debouncedSearch
                  ? `No${statusFilter !== "all" ? ` ${statusFilter}` : ""} documents match "${debouncedSearch}"${categoryFilter !== "all" ? " in this category" : ""}.`
                  : `No ${statusFilter !== "all" ? statusFilter : ""}${categoryFilter !== "all" ? " matching" : ""} documents.`
              }
              clearLabel="Clear filters"
              onClear={() => {
                setSearchInput("")
                setStatusFilter("all")
                setCategoryFilter("all")
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
                  <TableHead className="w-32">Category</TableHead>
                  <TableHead className="w-28">Status</TableHead>
                  <TableHead className="w-20">Pages</TableHead>
                  <TableHead className="w-24">Uploaded</TableHead>
                  <TableHead className="w-36"></TableHead>
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
                    onPreview={setPreviewDoc}
                    onReplace={requestReplace}
                    isReplacing={replaceTargetDoc?.document_id === doc.document_id && replaceMutation.isPending}
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
              <TableHead className="w-32">Category</TableHead>
              <TableHead className="w-28">Status</TableHead>
              <TableHead className="w-20">Pages</TableHead>
              <TableHead className="w-24">Uploaded</TableHead>
              <TableHead className="w-36"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableSkeletonRows columns={7} />
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

      <DocumentPreviewDialog
        doc={previewDoc}
        collegeId={college?.college_id}
        open={!!previewDoc}
        onOpenChange={(open) => !open && setPreviewDoc(null)}
      />
    </div>
  )
}

function DocumentRow({
  doc,
  isSelected,
  onToggleSelected,
  onDelete,
  isDeleting,
  onView,
  isViewing,
  onRetry,
  isRetrying,
  onPreview,
  onReplace,
  isReplacing,
}) {
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
        {doc.category ? (
          <Badge variant="outline" className="font-normal">
            {doc.category}
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
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
          {doc.status === "success" && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Preview extracted content for ${doc.file_name}`}
              title="Preview what got extracted"
              onClick={() => onPreview(doc)}
            >
              <FileSearch className="size-4 text-muted-foreground" />
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Replace ${doc.file_name} with a new file`}
            title="Replace with a new file"
            disabled={isReplacing}
            onClick={() => onReplace(doc)}
          >
            {isReplacing ? <Loader2 className="size-4 animate-spin" /> : <FileUp className="size-4 text-muted-foreground" />}
          </Button>
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
