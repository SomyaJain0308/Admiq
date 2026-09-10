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
                // Bubble shape matches the WhatsApp-mock hero on the
                // marketing landing page (home/index.html: .bubble) - one
                // corner near the sender's own side stays sharp instead of
                // every corner sharing the same radius, which is what
                // actually reads as a chat bubble rather than a rounded
                // rectangle. The real, authenticated view of a real
                // conversation should feel at least as close to WhatsApp
                // as the marketing page's mockup of it.
                "max-w-md rounded-xl px-3.5 py-2 text-sm whitespace-pre-wrap shadow-sm",
                isStudent
                  ? "rounded-bl-sm bg-muted text-foreground"
                  : message.messager_role === "staff"
                    ? "rounded-br-sm bg-accent text-accent-foreground"
                    : "rounded-br-sm bg-primary text-primary-foreground"
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
