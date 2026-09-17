import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocumentChunks } from "@/hooks/useDocuments"

// Shows the actual chunks the assistant indexed from a document - not just
// the pass/fail quality score shown in the table row. This is what lets
// staff catch a bad extraction (garbled OCR, a table that fell apart, a
// section that got dropped) before a student ever gets a wrong answer
// built from it.
export function DocumentPreviewDialog({ doc, collegeId, open, onOpenChange }) {
  const { data, isLoading, isError, error } = useDocumentChunks(collegeId, doc?.document_id, open)
  const chunks = data?.chunks || []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Extracted content</DialogTitle>
          <DialogDescription>
            What the assistant actually indexed from &quot;{doc?.file_name}&quot; - {chunks.length > 0 ? `${chunks.length} chunk${chunks.length === 1 ? "" : "s"}` : "review this before students start seeing answers from it"}.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {isLoading && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}

          {isError && (
            <p role="alert" className="text-sm text-destructive">
              {error?.message || "Failed to load extracted content."}
            </p>
          )}

          {!isLoading && !isError && chunks.length === 0 && (
            <p className="text-sm text-muted-foreground">No extracted chunks found for this document yet.</p>
          )}

          {!isLoading &&
            !isError &&
            chunks.map((chunk) => (
              <div key={chunk.chunk_id} className="rounded-md border bg-muted/30 p-3 text-sm">
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">Chunk {chunk.chunk_index + 1}</p>
                <p className="whitespace-pre-wrap">{chunk.content}</p>
              </div>
            ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
