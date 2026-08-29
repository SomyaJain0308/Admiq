import { useState } from "react"
import { Inbox, Loader2 } from "lucide-react"
import { useCurrentCollege } from "@/hooks/useCurrentCollege"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { ReplyToQueryDialog } from "@/components/ReplyToQueryDialog"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"

export default function LowConfidenceQueue() {
  const { college, hasNoCollege } = useCurrentCollege()
  const { data: queries, isLoading, isError, error } = useLowConfidenceQueries(college?.college_id)
  const [activeQuery, setActiveQuery] = useState(null)

  if (hasNoCollege) {
    return (
      <EmptyState
        title="No college access yet"
        description="Your account isn't linked to a college yet. Contact an admin to get set up."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Low-confidence queue</h1>
        <p className="text-muted-foreground">
          Questions the assistant wasn't confident enough to answer on its own, for {college.college_name}.
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading queue...
        </div>
      )}

      {isError && (
        <p className="text-sm text-destructive">
          {error?.message || "Failed to load the queue. Please try again."}
        </p>
      )}

      {!isLoading && !isError && queries?.length === 0 && (
        <EmptyState
          title="Nothing waiting on you"
          description="Every flagged question has been resolved. New ones will show up here automatically."
        />
      )}

      {!isLoading && queries?.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Question</TableHead>
              <TableHead>Assistant's answer</TableHead>
              <TableHead className="w-24"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queries.map((query) => (
              <TableRow key={query.query_id}>
                <TableCell className="max-w-xs whitespace-normal">{query.question_content}</TableCell>
                <TableCell className="max-w-xs whitespace-normal text-muted-foreground">
                  {query.answer_content}
                </TableCell>
                <TableCell>
                  <Button size="sm" onClick={() => setActiveQuery(query)}>
                    Reply
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <ReplyToQueryDialog
        query={activeQuery}
        collegeId={college?.college_id}
        open={!!activeQuery}
        onOpenChange={(open) => !open && setActiveQuery(null)}
      />
    </div>
  )
}

function EmptyState({ title, description }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
      <Inbox className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
