import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Search, Sparkles, Users } from "lucide-react"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import { useResolveLowConfidenceQuery, useReplySuggestions, useKnowledgeSearch } from "@/hooks/useLowConfidenceQueue"
import { useConversation } from "@/hooks/useStudents"
import { StudentSnapshotCard } from "@/components/StudentSnapshot"
import { ConversationView } from "@/components/ConversationView"
import { defaultExpiryDate, today } from "@/lib/dates"
import { cn } from "@/lib/utils"

// WhatsApp's own hard limit on a single text message - matches the cap
// already enforced on the direct-message box (MessageStudentBox), so a
// staff reply here can't fail on send for a reason that was invisible while
// typing it.
const MAX_REPLY_LENGTH = 4096

// A distance this close basically means "this is the same question" -
// worth calling out as a strong match rather than just one option among
// several.
const STRONG_MATCH_DISTANCE = 0.2

// `similarGroup` (optional) is the rest of a "these look like the same
// question" cluster from the similar-groups endpoint - other open queries,
// from other students, that this one reply should also resolve. Passing it
// turns this into a bulk reply: every member gets the same message sent to
// them and gets marked resolved alongside the primary query.
export function ReplyToQueryDialog({ query, collegeId, open, onOpenChange, similarGroup }) {
  const [replyMessage, setReplyMessage] = useState("")
  // Most staff answers are just as true next month as they are today, so
  // "never expires" (expires_at = null, which the backend already treats as
  // always-retrievable) is the sane default - an expiry date is something
  // you opt into for answers you know are time-bound (a deadline, an event,
  // a temporary policy), not something you have to remember to clear.
  const [hasExpiry, setHasExpiry] = useState(false)
  const [expiresAt, setExpiresAt] = useState(defaultExpiryDate())
  const [showKnowledgeSearch, setShowKnowledgeSearch] = useState(false)
  const [knowledgeSearchInput, setKnowledgeSearchInput] = useState("")
  const [knowledgeSearchTerm, setKnowledgeSearchTerm] = useState("")
  const resolveMutation = useResolveLowConfidenceQuery(collegeId)

  const additionalMembers = (similarGroup || []).filter((m) => m.query_id !== query?.query_id)

  // Only enabled while a query is actually loaded (useConversation already
  // guards on studentId), so this doesn't fetch anything while the dialog
  // is closed.
  const { data: messages, isLoading: convoLoading } = useConversation(collegeId, query?.student_id)

  // Draft-assist: retrieval already ran once to flag this question in the
  // first place - show the closest existing knowledge-base matches so
  // staff can 1-click "use this" or edit instead of typing from scratch.
  const { data: suggestionData, isLoading: suggestionsLoading } = useReplySuggestions(collegeId, query?.query_id, {
    enabled: open,
  })
  const suggestions = suggestionData?.suggestions || []

  // Debounce the staff-typed knowledge-base search so every keystroke
  // doesn't fire a request - only settle on a term once typing pauses.
  useEffect(() => {
    const handle = setTimeout(() => setKnowledgeSearchTerm(knowledgeSearchInput), 350)
    return () => clearTimeout(handle)
  }, [knowledgeSearchInput])
  const { data: knowledgeData, isLoading: knowledgeLoading, isFetching: knowledgeFetching } = useKnowledgeSearch(
    collegeId,
    knowledgeSearchTerm,
    { enabled: open && showKnowledgeSearch }
  )
  const knowledgeResults = knowledgeData?.results || []

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
      setShowKnowledgeSearch(false)
      setKnowledgeSearchInput("")
      setKnowledgeSearchTerm("")
      resolveMutation.reset()
    }
    onOpenChange(next)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      const result = await resolveMutation.mutateAsync({
        queryId: query.query_id,
        replyMessage,
        expiresAt: hasExpiry ? new Date(expiresAt).toISOString() : null,
        additionalQueryIds: additionalMembers.map((m) => m.query_id),
      })
      // The reply always sends even if saving it as a reusable answer
      // fails behind the scenes (e.g. a flaky LLM call) - surface that
      // distinction so staff know if they need to re-save it, instead of
      // assuming a generic success toast means both things happened.
      if (result?.save_error) {
        toast.warning("Reply sent, but it wasn't saved for future students.", {
          description: result.save_error,
        })
      } else if (result?.conflicts_flagged > 0) {
        toast.warning("Reply sent, but it looks like it conflicts with something already saved.", {
          description: "Check the Conflicts page to review it.",
        })
      } else if (additionalMembers.length > 0) {
        toast.success(`Reply sent to ${additionalMembers.length + 1} students.`)
      } else {
        toast.success("Reply sent to student.")
      }
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

          {additionalMembers.length > 0 && (
            <div className="flex flex-col gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
              <p className="flex items-center gap-1.5 font-medium">
                <Users className="size-4" />
                {additionalMembers.length} other student{additionalMembers.length === 1 ? "" : "s"} asked basically the same thing
              </p>
              <p className="text-xs text-muted-foreground">
                Sending this reply will also answer and resolve their questions - no need to type it again.
              </p>
              <ul className="flex flex-col gap-1 pl-1 text-xs text-muted-foreground">
                {additionalMembers.map((member) => (
                  <li key={member.query_id} className="line-clamp-1">
                    &bull; {member.question_content}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(suggestionsLoading || suggestions.length > 0) && (
            <div className="flex flex-col gap-2 rounded-md border p-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Sparkles className="size-3.5" />
                Similar to what's already in the knowledge base
              </p>
              {suggestionsLoading ? (
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  {suggestions.map((suggestion) => (
                    <div key={suggestion.chunk_id} className="flex flex-col gap-1 rounded-md border bg-muted/20 p-2">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-xs font-medium text-muted-foreground">{suggestion.source_label}</span>
                        {suggestion.distance <= STRONG_MATCH_DISTANCE && (
                          <Badge variant="secondary" className="shrink-0 text-[10px]">
                            Close match
                          </Badge>
                        )}
                      </div>
                      <p className="line-clamp-2 text-sm">{suggestion.answer_text}</p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="self-start"
                        onClick={() => setReplyMessage(suggestion.answer_text)}
                      >
                        Use this
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="reply">Your reply</Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-auto gap-1 px-1.5 py-0.5 text-xs text-muted-foreground"
                  onClick={() => setShowKnowledgeSearch((v) => !v)}
                >
                  <Search className="size-3.5" />
                  {showKnowledgeSearch ? "Hide" : "Search"} knowledge base
                </Button>
              </div>
              {showKnowledgeSearch && (
                <div className="flex flex-col gap-2 rounded-md border bg-muted/20 p-2">
                  <Input
                    autoFocus
                    value={knowledgeSearchInput}
                    onChange={(e) => setKnowledgeSearchInput(e.target.value)}
                    placeholder="Search everything we already know, e.g. hostel fees"
                  />
                  {knowledgeSearchInput.trim().length > 0 && knowledgeSearchInput.trim().length < 2 && (
                    <p className="text-xs text-muted-foreground">Keep typing to search.</p>
                  )}
                  {(knowledgeLoading || knowledgeFetching) && knowledgeSearchTerm.trim().length >= 2 && (
                    <Skeleton className="h-10 w-full" />
                  )}
                  {!knowledgeLoading && knowledgeSearchTerm.trim().length >= 2 && knowledgeResults.length === 0 && (
                    <p className="text-xs text-muted-foreground">Nothing in the knowledge base matches that yet.</p>
                  )}
                  {!knowledgeLoading &&
                    knowledgeResults.map((result) => (
                      <div key={result.chunk_id} className="flex flex-col gap-1 rounded-md border bg-background p-2">
                        <span className="text-xs font-medium text-muted-foreground">{result.source_label}</span>
                        <p className="line-clamp-2 text-sm">{result.answer_text}</p>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="self-start"
                          onClick={() => setReplyMessage(result.answer_text)}
                        >
                          Use this
                        </Button>
                      </div>
                    ))}
                </div>
              )}
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
                className={cn(
                  "self-end text-xs",
                  replyMessage.length >= MAX_REPLY_LENGTH ? "text-destructive" : "text-muted-foreground"
                )}
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
                {resolveMutation.isPending
                  ? "Sending..."
                  : additionalMembers.length > 0
                    ? `Send reply to ${additionalMembers.length + 1} students`
                    : "Send reply"}
              </Button>
            </DialogFooter>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}
