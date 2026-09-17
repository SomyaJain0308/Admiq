import { useEffect, useState } from "react"
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
import { useCreateKnowledgeBaseEntry, useUpdateKnowledgeBaseEntry } from "@/hooks/useKnowledgeBase"
import { defaultExpiryDate, today } from "@/lib/dates"

const emptyForm = { question: "", answer: "" }

// Shared by the "Add Q&A" flow (staff teaching the assistant something
// proactively, e.g. ahead of a deadline they know students will ask about)
// and editing an existing entry from the knowledge-base list - same fields,
// just a different mutation and different defaults underneath.
export function KnowledgeBaseEntryDialog({ collegeId, open, onOpenChange, editingEntry }) {
  const isEditMode = !!editingEntry
  const [form, setForm] = useState(emptyForm)
  const [hasExpiry, setHasExpiry] = useState(false)
  const [expiresAt, setExpiresAt] = useState(defaultExpiryDate())

  const createMutation = useCreateKnowledgeBaseEntry(collegeId)
  const updateMutation = useUpdateKnowledgeBaseEntry(collegeId)
  const mutation = isEditMode ? updateMutation : createMutation

  useEffect(() => {
    if (open) {
      setForm(isEditMode ? { question: editingEntry.question, answer: editingEntry.answer } : emptyForm)
      const existingExpiry = isEditMode && editingEntry.expires_at ? editingEntry.expires_at.slice(0, 10) : null
      setHasExpiry(!!existingExpiry)
      setExpiresAt(existingExpiry || defaultExpiryDate())
      mutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editingEntry])

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      if (isEditMode) {
        const updates = { question: form.question, answer: form.answer }
        if (hasExpiry) {
          updates.expires_at = new Date(expiresAt).toISOString()
        } else if (editingEntry.expires_at) {
          // Only clear it if it actually had one - avoids sending
          // clear_expiry on every save of an entry that never had an expiry.
          updates.clear_expiry = true
        }
        const result = await updateMutation.mutateAsync({ chunkId: editingEntry.chunk_id, updates })
        if (result?.conflicts_flagged > 0) {
          toast.warning("Saved, but it looks like it conflicts with something already in the knowledge base.", {
            description: "Check the Conflicts page to review it.",
          })
        } else {
          toast.success("Knowledge base entry updated.")
        }
      } else {
        const result = await createMutation.mutateAsync({
          question: form.question,
          answer: form.answer,
          expires_at: hasExpiry ? new Date(expiresAt).toISOString() : null,
        })
        if (result?.conflicts_flagged > 0) {
          toast.warning("Added, but it looks like it conflicts with something already in the knowledge base.", {
            description: "Check the Conflicts page to review it.",
          })
        } else {
          toast.success("Added to the knowledge base.")
        }
      }
      onOpenChange(false)
    } catch {
      // error is captured in mutation.error and shown below
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{isEditMode ? "Edit knowledge base entry" : "Add a Q&A"}</DialogTitle>
          <DialogDescription>
            {isEditMode
              ? "Changes are re-indexed right away - the assistant uses the updated wording for the next matching question."
              : "Teach the assistant something ahead of time, without waiting for a student to ask first."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="kb-question">Question</Label>
            <Textarea
              id="kb-question"
              required
              rows={2}
              maxLength={2000}
              value={form.question}
              onChange={(e) => setForm((f) => ({ ...f, question: e.target.value }))}
              placeholder="e.g. When is the scholarship application deadline?"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="kb-answer">Answer</Label>
            <Textarea
              id="kb-answer"
              required
              rows={4}
              maxLength={4000}
              value={form.answer}
              onChange={(e) => setForm((f) => ({ ...f, answer: e.target.value }))}
              placeholder="The answer the assistant should give students who ask this."
            />
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <Checkbox id="kb-has-expiry" checked={hasExpiry} onCheckedChange={(checked) => setHasExpiry(checked === true)} />
              <Label htmlFor="kb-has-expiry" className="font-normal">
                Stop using this answer for future students after a date
              </Label>
            </div>
            {hasExpiry ? (
              <input
                id="kb-expires"
                type="date"
                required
                min={today()}
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="border-input flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
              />
            ) : (
              <p className="pl-6 text-xs text-muted-foreground">By default, this answer stays available to the assistant indefinitely.</p>
            )}
          </div>

          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive">
              {mutation.error?.message || "Something went wrong. Please try again."}
            </p>
          )}

          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving..." : isEditMode ? "Save changes" : "Add to knowledge base"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
