import { useState } from "react"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { useResolveLowConfidenceQuery } from "@/hooks/useLowConfidenceQueue"

function defaultExpiryDate() {
  const d = new Date()
  d.setDate(d.getDate() + 30)
  return d.toISOString().slice(0, 10) // yyyy-mm-dd, for <input type="date">
}

export function ReplyToQueryDialog({ query, collegeId, open, onOpenChange }) {
  const [replyMessage, setReplyMessage] = useState("")
  const [expiresAt, setExpiresAt] = useState(defaultExpiryDate())
  const resolveMutation = useResolveLowConfidenceQuery(collegeId)

  function handleOpenChange(next) {
    if (!next) {
      setReplyMessage("")
      setExpiresAt(defaultExpiryDate())
      resolveMutation.reset()
    }
    onOpenChange(next)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      await resolveMutation.mutateAsync({
        queryId: query.query_id,
        replyMessage,
        expiresAt: new Date(expiresAt).toISOString(),
      })
      toast.success("Reply sent to student.")
      handleOpenChange(false)
    } catch {
      // error is already captured in resolveMutation.error and shown below
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Reply to student</DialogTitle>
          <DialogDescription>
            This reply is sent to the student on WhatsApp right away, and gets saved so the assistant can use it for similar questions in the future.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="rounded-md border bg-muted/30 p-3 text-sm">
            <p className="font-medium">Student asked:</p>
            <p className="text-muted-foreground">{query?.question_content}</p>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="reply">Your reply</Label>
              <Textarea
                id="reply"
                required
                rows={4}
                value={replyMessage}
                onChange={(e) => setReplyMessage(e.target.value)}
                placeholder="Type the answer to send to the student..."
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="expires">Keep this answer available for future students until</Label>
              <input
                id="expires"
                type="date"
                required
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="border-input flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
              />
            </div>

            {resolveMutation.isError && (
              <p className="text-sm text-destructive">
                {resolveMutation.error?.message || "Failed to send reply. Please try again."}
              </p>
            )}

            <DialogFooter>
              <Button type="submit" disabled={resolveMutation.isPending}>
                {resolveMutation.isPending ? "Sending..." : "Send reply"}
              </Button>
            </DialogFooter>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}
