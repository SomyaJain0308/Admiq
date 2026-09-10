import { useState } from "react"
import { toast } from "sonner"
import { Loader2 } from "lucide-react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useUpdateStudentNotes } from "@/hooks/useStudents"
import { cn } from "@/lib/utils"

const MAX_NOTES_LENGTH = 5000

export function InternalNotesCard({ collegeId, studentId, initialNotes }) {
  const [notes, setNotes] = useState(initialNotes || "")
  const notesMutation = useUpdateStudentNotes(collegeId, studentId)
  const isDirty = notes !== (initialNotes || "")
  const isNearLimit = notes.length >= MAX_NOTES_LENGTH - 200

  async function handleSave() {
    try {
      await notesMutation.mutateAsync(notes.trim() === "" ? null : notes)
      toast.success("Note saved.")
    } catch {
      // error is already captured in notesMutation.error and shown below
    }
  }

  return (
    <Card className="shadow-elevated">
      <CardHeader>
        <CardTitle className="font-display text-base">Internal notes</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <Textarea
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes only your team can see — call outcomes, follow-up plans, concerns raised..."
          maxLength={MAX_NOTES_LENGTH}
          disabled={notesMutation.isPending}
        />
        {isNearLimit && (
          <span
            className={cn("self-end text-xs", notes.length >= MAX_NOTES_LENGTH ? "text-destructive" : "text-muted-foreground")}
          >
            {notes.length}/{MAX_NOTES_LENGTH}
          </span>
        )}
        {notesMutation.isError && (
          <p role="alert" className="text-sm text-destructive">
            {notesMutation.error?.message || "Failed to save note. Please try again."}
          </p>
        )}
        <div className="flex justify-end">
          <Button size="sm" onClick={handleSave} disabled={!isDirty || notesMutation.isPending}>
            {notesMutation.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Saving...
              </>
            ) : (
              "Save note"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
