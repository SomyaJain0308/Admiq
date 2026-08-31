import { cn } from "@/lib/utils"

function formatTimestamp(iso) {
  if (!iso) return ""
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

export function ConversationView({ messages }) {
  if (!messages || messages.length === 0) {
    return <p className="text-sm text-muted-foreground">No conversation history yet.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {messages.map((message) => {
        const isStudent = message.messager_role === "student"
        return (
          <div
            key={message.message_id}
            className={cn("flex flex-col gap-1", isStudent ? "items-start" : "items-end")}
          >
            <div
              className={cn(
                "max-w-md rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
                isStudent
                  ? "bg-muted text-foreground"
                  : message.messager_role === "staff"
                    ? "bg-blue-600 text-white"
                    : "bg-primary text-primary-foreground"
              )}
            >
              {message.content}
            </div>
            <span className="px-1 text-xs text-muted-foreground">
              {message.messager_role === "student" ? "Student" : message.messager_role === "staff" ? "Staff" : "Assistant"} · {formatTimestamp(message.created_at)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
