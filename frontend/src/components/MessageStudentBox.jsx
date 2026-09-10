import { useState } from "react"
import { toast } from "sonner"
import { Loader2, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { useMessageStudent, useConversation } from "@/hooks/useStudents"
import { defaultExpiryDate, today } from "@/lib/dates"

export function MessageStudentBox({ collegeId, studentId }) {
  const [content, setContent] = useState("")
  const [saveAsAnswer, setSaveAsAnswer] = useState(false)
  const [hasExpiry, setHasExpiry] = useState(false)
  const [expiresAt, setExpiresAt] = useState(defaultExpiryDate())
  const messageMutation = useMessageStudent(collegeId, studentId)

  // Saving as a reusable answer needs a real student message in this
  // conversation to anchor to (see the backend - it points
  // LowConfidenceQuery.question_message_id at the student's most recent
  // message here). A purely cold outreach - staff messaging a student who
  // has never replied - has nothing to anchor to, so the checkbox is
  // disabled rather than letting staff check it and hit an error on send.
  const { data: messages } = useConversation(collegeId, studentId)
  const hasStudentMessage = (messages || []).some((m) => m.messager_role === "student")

  function resetSaveAsAnswer() {
    setSaveAsAnswer(false)
    setHasExpiry(false)
    setExpiresAt(defaultExpiryDate())
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const trimmed = content.trim()
    if (!trimmed) return
    try {
      const result = await messageMutation.mutateAsync({
        content: trimmed,
        saveAsAnswer: saveAsAnswer && hasStudentMessage,
        expiresAt: hasExpiry ? new Date(expiresAt).toISOString() : null,
      })
      setContent("")
      resetSaveAsAnswer()

      if (result?.delivered === false) {
        toast.warning("Message saved, but WhatsApp delivery failed. The student may not have received it.")
      } else if (result?.channel === "template") {
        // WhatsApp only allows free-form text within 24h of the student's
        // last message - past that, the send falls back to the approved
        // template, which reads differently to the student than what was
        // typed here (the typed text fills the template's one variable but
        // is wrapped in the template's own fixed wording).
        toast.success("Sent via template — this student hasn't messaged in over 24h, so WhatsApp required an approved template instead of your exact text.")
      } else {
        toast.success("Message sent.")
      }

      if (saveAsAnswer && hasStudentMessage) {
        if (result?.saved_as_answer) {
          toast.success("Saved as a reusable answer for future students.")
        } else if (result?.save_error) {
          toast.warning(result.save_error)
        }
      }
    } catch {
      // error is already captured in messageMutation.error and shown below
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 border-t pt-3">
      <Textarea
        rows={2}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Message this student on WhatsApp..."
        maxLength={4096}
        disabled={messageMutation.isPending}
      />

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Checkbox
            id="save-as-answer"
            checked={saveAsAnswer}
            disabled={messageMutation.isPending || !hasStudentMessage}
            onCheckedChange={(checked) => {
              const next = checked === true
              setSaveAsAnswer(next)
              if (!next) {
                setHasExpiry(false)
                setExpiresAt(defaultExpiryDate())
              }
            }}
          />
          <Label htmlFor="save-as-answer" className="font-normal">
            Save this as a reusable answer
          </Label>
        </div>
        {!hasStudentMessage ? (
          <p className="pl-6 text-xs text-muted-foreground">
            This student hasn't sent a message yet, so there's nothing here for the assistant to generalize from.
          </p>
        ) : saveAsAnswer ? (
          <>
            <p className="pl-6 text-xs text-muted-foreground">
              The assistant will be able to use this to answer similar questions from other students.
            </p>
            <div className="flex items-center gap-2 pl-6">
              <Checkbox
                id="has-expiry"
                checked={hasExpiry}
                disabled={messageMutation.isPending}
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
                disabled={messageMutation.isPending}
                className="ml-6 border-input flex h-9 rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
              />
            ) : (
              <p className="pl-6 text-xs text-muted-foreground">By default, this answer stays available to the assistant indefinitely.</p>
            )}
          </>
        ) : null}
      </div>

      {messageMutation.isError && (
        <p role="alert" className="text-sm text-destructive">
          {messageMutation.error?.message || "Failed to send message. Please try again."}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="submit" size="sm" disabled={messageMutation.isPending || !content.trim()}>
          {messageMutation.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Sending...
            </>
          ) : (
            <>
              <Send className="size-4" />
              Send
            </>
          )}
        </Button>
      </div>
    </form>
  )
}
