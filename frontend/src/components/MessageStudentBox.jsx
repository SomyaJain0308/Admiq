import { useState } from "react"
import { toast } from "sonner"
import { Loader2, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useMessageStudent } from "@/hooks/useStudents"

export function MessageStudentBox({ collegeId, studentId }) {
  const [content, setContent] = useState("")
  const messageMutation = useMessageStudent(collegeId, studentId)

  async function handleSubmit(e) {
    e.preventDefault()
    const trimmed = content.trim()
    if (!trimmed) return
    try {
      const result = await messageMutation.mutateAsync(trimmed)
      setContent("")
      if (result?.delivered === false) {
        toast.warning("Message saved, but WhatsApp delivery failed. The student may not have received it.")
      } else {
        toast.success("Message sent.")
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
