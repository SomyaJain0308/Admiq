import { useEffect, useRef } from "react"
import { useParams, Link } from "react-router-dom"
import { ArrowLeft, Loader2 } from "lucide-react"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useStudentDetail, useConversation } from "@/hooks/useStudents"
import { ConversationView } from "@/components/ConversationView"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { leadScoreBand } from "@/lib/leadScore"

export default function StudentDetail() {
  const { studentId } = useParams()
  const { college } = useCurrentCollege()
  const { data: student, isLoading: studentLoading, isError: studentError } = useStudentDetail(college?.college_id, studentId)
  const { data: messages, isLoading: convoLoading } = useConversation(college?.college_id, studentId)
  const conversationRef = useRef(null)

  // Jump to the most recent message once the conversation loads, and again
  // any time it changes (e.g. after replying from the low-confidence queue) -
  // otherwise a long thread opens scrolled to the oldest message instead of
  // where the actual context for helping this student is.
  useEffect(() => {
    if (conversationRef.current) {
      conversationRef.current.scrollTop = conversationRef.current.scrollHeight
    }
  }, [messages])

  if (studentLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading student...
      </div>
    )
  }

  if (studentError || !student) {
    return <p role="alert" className="text-sm text-destructive">Student not found.</p>
  }

  const band = leadScoreBand(student.lead_score ?? 0)
  const signals = student.profile_signals || {}
  const academicScores = student.academic_scores || {}

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/students" className="mb-2 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" />
          Back to students
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{student.student_name || "Unnamed student"}</h1>
          <Badge variant="outline" className={band.className}>
            {student.lead_score ?? 0} · {band.label}
          </Badge>
        </div>
        <p className="text-muted-foreground">{student.student_phone}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>Conversation</CardTitle>
          </CardHeader>
          <CardContent>
            {convoLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading conversation...
              </div>
            ) : (
              <div ref={conversationRef} className="max-h-[600px] overflow-y-auto pr-1">
                <ConversationView messages={messages} />
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Profile</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <Field label="Course interest" value={student.course_interest} />
              {Object.keys(academicScores).length > 0 && (
                <div>
                  <p className="mb-1 font-medium">Academic scores</p>
                  {Object.entries(academicScores).map(([key, value]) => (
                    <p key={key} className="text-muted-foreground">
                      {key.replaceAll("_", " ")}: {value}
                    </p>
                  ))}
                </div>
              )}
              {student.summary && (
                <div>
                  <p className="mb-1 font-medium">Summary</p>
                  <p className="text-muted-foreground">{student.summary}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Signals for staff</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <ListField label="Open concerns" items={signals.concerns} />
              <Field label="Guardian involvement" value={signals.guardian_involvement} />
              <ListField label="Competing colleges" items={signals.competing_colleges} />
              <Field label="Drop-off reason" value={signals.dropoff_reason} />
              {!signals.concerns?.length && !signals.guardian_involvement && !signals.competing_colleges?.length && !signals.dropoff_reason && (
                <p className="text-muted-foreground">No signals recorded yet.</p>
              )}
            </CardContent>
          </Card>

          {student.internal_notes && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Internal notes</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{student.internal_notes}</CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ label, value }) {
  if (!value) return null
  return (
    <div>
      <p className="font-medium">{label}</p>
      <p className="text-muted-foreground">{value}</p>
    </div>
  )
}

function ListField({ label, items }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <p className="font-medium">{label}</p>
      <ul className="list-inside list-disc text-muted-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
