import { useRef, useState } from "react"
import { FileText, Loader2, CheckCircle2, XCircle, Upload } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useDocuments, useUploadDocument } from "@/hooks/useDocuments"
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
  const fileInputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)

  const { page, setPage, totalPages, pageItems } = usePagination(documents || [], 15)

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
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={4} />
            ) : (
              pageItems.map((doc) => <DocumentRow key={doc.document_id} doc={doc} />)
            )}
          </TableBody>
        </Table>
      )}

      {!isLoading && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}
    </div>
  )
}

function DocumentRow({ doc }) {
  return (
    <TableRow>
      <TableCell className="max-w-xs truncate font-medium" title={doc.error || undefined}>
        {doc.file_name}
      </TableCell>
      <TableCell>
        <StatusBadge status={doc.status} error={doc.error} />
      </TableCell>
      <TableCell className="text-muted-foreground">{doc.num_pages ?? "-"}</TableCell>
      <TableCell className="text-muted-foreground">{timeSince(doc.created_at)}</TableCell>
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
