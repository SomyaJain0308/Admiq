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
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { useResolveLowConfidenceQuery } from "@/hooks/useLowConfidenceQueue"
import { useConversation } from "@/hooks/useStudents"
import { StudentSnapshotCard } from "@/components/StudentSnapshot"
import { ConversationView } from "@/components/ConversationView"

function defaultExpiryDate() {
  const d = new Date()
  d.setDate(d.getDate() + 30)
  return d.toISOString().slice(0, 10) // yyyy-mm-dd, for <input type="date">
}

function today() {
  return new Date().toISOString().slice(0, 10)
}

// WhatsApp's own hard limit on a single text message - matches the cap
// already enforced on the direct-message box (MessageStudentBox), so a
// staff reply here can't fail on send for a reason that was invisible while
// typing it.
const MAX_REPLY_LENGTH = 4096

export function ReplyToQueryDialog({ query, collegeId, open, onOpenChange }) {
  const [replyMessage, setReplyMessage] = useState("")
  // Most staff answers are just as true next month as they are today, so
  // "never expires" (expires_at = null, which the backend already treats as
  // always-retrievable) is the sane default - an expiry date is something
  // you opt into for answers you know are time-bound (a deadline, an event,
  // a temporary policy), not something you have to remember to clear.
  const [hasExpiry, setHasExpiry] = useState(false)
  const [expiresAt, setExpiresAt] = useState(defaultExpiryDate())
  const resolveMutation = useResolveLowConfidenceQuery(collegeId)

  // Only enabled while a query is actually loaded (useConversation already
  // guards on studentId), so this doesn't fetch anything while the dialog
  // is closed.
  const { data: messages, isLoading: convoLoading } = useConversation(collegeId, query?.student_id)

  // What led up to this flagged question - not the question itself, which
  // gets its own highlighted box below. Without this, staff replying only
  // ever see the single question in isolation, with no sense of what the
  // student already said earlier in the thread that gives it context.
  const priorMessages = query?.question_message_id
    ? (messages || []).filter((m) => m.message_id < query.question_message_id).slice(-5)
    : []

  function handleOpenChange(next) {
    if (!next) {
      setReplyMessage("")
      setHasExpiry(false)
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
        expiresAt: hasExpiry ? new Date(expiresAt).toISOString() : null,
      })
      toast.success("Reply sent to student.")
      handleOpenChange(false)
    } catch {
      // error is already captured in resolveMutation.error and shown below
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Reply to student</DialogTitle>
          <DialogDescription>
            This reply is sent to the student on WhatsApp right away, and gets saved so the assistant can use it for similar questions in the future.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {query?.student_id != null && (
            <StudentSnapshotCard collegeId={collegeId} studentId={query.student_id} />
          )}

          {convoLoading ? (
            <div className="flex flex-col gap-2 rounded-md border p-3">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-3/4" />
            </div>
          ) : (
            priorMessages.length > 0 && (
              <div className="flex flex-col gap-2 rounded-md border p-3">
                <p className="text-xs font-medium text-muted-foreground">Earlier in this conversation</p>
                <div className="max-h-48 overflow-y-auto pr-1">
                  <ConversationView messages={priorMessages} />
                </div>
              </div>
            )
          )}

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
                maxLength={MAX_REPLY_LENGTH}
                value={replyMessage}
                onChange={(e) => setReplyMessage(e.target.value)}
                placeholder="Type the answer to send to the student..."
              />
              <span
                className={`self-end text-xs ${
                  replyMessage.length >= MAX_REPLY_LENGTH ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {replyMessage.length}/{MAX_REPLY_LENGTH}
              </span>
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="has-expiry"
                  checked={hasExpiry}
                  onCheckedChange={(checked) => setHasExpiry(checked === true)}
                />
                <Label htmlFor="has-expiry" className="font-normal">
                  Stop using this answer for future students after a date
                </Label>
              </div>
              {hasExpiry ? (
                <input
                  id="expires"
                  type="date"
                  required
                  min={today()}
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  className="border-input flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                />
              ) : (
                <p className="pl-6 text-xs text-muted-foreground">
                  By default, this answer stays available to the assistant indefinitely.
                </p>
              )}
            </div>

            {resolveMutation.isError && (
              <p role="alert" className="text-sm text-destructive">
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
