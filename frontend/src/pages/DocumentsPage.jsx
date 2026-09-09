import { useRef, useState } from "react"
import { FileText, Loader2, CheckCircle2, XCircle, Upload, Trash2, Eye } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useDocuments, useUploadDocument, useDeleteDocument, useViewDocument } from "@/hooks/useDocuments"
import { usePagination } from "@/hooks/usePagination"
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

const MAX_FILE_SIZE_MB = 25

export default function DocumentsPage() {
  const { college, hasNoCollege } = useCurrentCollege()
  const { data: documents, isLoading, isError, error } = useDocuments(college?.college_id)
  const uploadMutation = useUploadDocument(college?.college_id)
  const deleteMutation = useDeleteDocument(college?.college_id)
  const viewMutation = useViewDocument(college?.college_id)
  const fileInputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)

  const { page, setPage, totalPages, pageItems } = usePagination(documents || [], 15)

  async function handleView(doc) {
    try {
      await viewMutation.mutateAsync(doc.document_id)
    } catch (err) {
      toast.error(err?.message || `Failed to open ${doc.file_name}.`)
    }
  }

  async function handleDelete(doc) {
    const confirmed = window.confirm(`Delete "${doc.file_name}"? The assistant will stop using it to answer questions - this can't be undone.`)
    if (!confirmed) return
    try {
      await deleteMutation.mutateAsync(doc.document_id)
      toast.success(`${doc.file_name} deleted.`)
    } catch (err) {
      toast.error(err?.message || "Failed to delete document.")
    }
  }

  async function handleFiles(fileList) {
    const files = Array.from(fileList || [])
    for (const file of files) {
      if (file.type !== "application/pdf") {
        toast.error(`${file.name} isn't a PDF - only PDF files are supported right now.`)
        continue
      }
      if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        toast.error(`${file.name} is too large - max ${MAX_FILE_SIZE_MB}MB at a time.`)
        continue
      }
      try {
        await uploadMutation.mutateAsync(file)
        toast.success(`${file.name} uploaded - processing now.`)
      } catch (err) {
        toast.error(err?.message || `Failed to upload ${file.name}. Please try again.`)
      }
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Documents</h1>
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
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed py-10 text-center transition-colors ${
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25"
        }`}
      >
        <Upload className="size-8 text-muted-foreground" />
        <div>
          <p className="font-medium">Drag and drop a PDF here</p>
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
          disabled={uploadMutation.isPending}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploadMutation.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Uploading...
            </>
          ) : (
            "Choose file"
          )}
        </Button>
      </div>

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load documents. Please try again."}
        </p>
      )}

      {!isLoading && !isError && documents?.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
          <FileText className="size-8 text-muted-foreground" />
          <p className="font-medium">No documents yet</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Upload a PDF above to get started - the assistant will use it to answer student questions.
          </p>
        </div>
      )}

      {(isLoading || pageItems.length > 0) && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>File</TableHead>
              <TableHead className="w-28">Status</TableHead>
              <TableHead className="w-20">Pages</TableHead>
              <TableHead className="w-24">Uploaded</TableHead>
              <TableHead className="w-20"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={5} />
            ) : (
              pageItems.map((doc) => (
                <DocumentRow
                  key={doc.document_id}
                  doc={doc}
                  onDelete={handleDelete}
                  isDeleting={deleteMutation.isPending && deleteMutation.variables === doc.document_id}
                  onView={handleView}
                  isViewing={viewMutation.isPending && viewMutation.variables === doc.document_id}
                />
              ))
            )}
          </TableBody>
        </Table>
      )}

      {!isLoading && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}
    </div>
  )
}

function DocumentRow({ doc, onDelete, isDeleting, onView, isViewing }) {
  return (
    <TableRow>
      <TableCell className="max-w-xs truncate font-medium" title={doc.error || undefined}>
        <button
          type="button"
          onClick={() => onView(doc)}
          disabled={isViewing}
          className="truncate text-left hover:underline disabled:cursor-wait disabled:no-underline disabled:opacity-70"
          title={`Open ${doc.file_name}`}
        >
          {doc.file_name}
        </button>
      </TableCell>
      <TableCell>
        <StatusBadge status={doc.status} error={doc.error} />
      </TableCell>
      <TableCell className="text-muted-foreground">{doc.num_pages ?? "-"}</TableCell>
      <TableCell className="text-muted-foreground">{timeSince(doc.created_at)}</TableCell>
      <TableCell>
        <div className="flex items-center">
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

function StatusBadge({ status, error }) {
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
      <Badge variant="destructive" className="gap-1" title={error || undefined}>
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
