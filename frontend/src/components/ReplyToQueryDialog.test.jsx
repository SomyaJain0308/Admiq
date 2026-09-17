import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { ReplyToQueryDialog } from "@/components/ReplyToQueryDialog"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const mockMutateAsync = vi.fn()
const mockReset = vi.fn()
let mockMutationState = { isPending: false, isError: false, error: null }
let mockSuggestionsState = { data: { suggestions: [] }, isLoading: false }
let mockKnowledgeSearchState = { data: { results: [] }, isLoading: false, isFetching: false }
vi.mock("@/hooks/useLowConfidenceQueue", () => ({
  useResolveLowConfidenceQuery: () => ({
    mutateAsync: mockMutateAsync,
    reset: mockReset,
    ...mockMutationState,
  }),
  useReplySuggestions: () => mockSuggestionsState,
  useKnowledgeSearch: () => mockKnowledgeSearchState,
}))

vi.mock("@/hooks/useStudents", () => ({
  useConversation: () => ({ data: [], isLoading: false }),
}))

// Both render real network/query-backed data in the full app - stubbed out
// here since this dialog's own reply flow doesn't depend on their contents.
vi.mock("@/components/StudentSnapshot", () => ({
  StudentSnapshotCard: () => <div data-testid="student-snapshot" />,
}))
vi.mock("@/components/ConversationView", () => ({
  ConversationView: () => <div data-testid="conversation-view" />,
}))

const QUERY = {
  query_id: 55,
  student_id: 101,
  question_content: "Does the hostel have AC rooms?",
  question_message_id: 900,
}

function renderDialog(props = {}) {
  const onOpenChange = vi.fn()
  const utils = render(
    <ReplyToQueryDialog query={QUERY} collegeId={1} open={true} onOpenChange={onOpenChange} {...props} />
  )
  return { onOpenChange, ...utils }
}

describe("ReplyToQueryDialog", () => {
  beforeEach(() => {
    mockMutateAsync.mockReset()
    mockReset.mockReset()
    mockMutationState = { isPending: false, isError: false, error: null }
    mockSuggestionsState = { data: { suggestions: [] }, isLoading: false }
    mockKnowledgeSearchState = { data: { results: [] }, isLoading: false, isFetching: false }
    toast.success.mockReset()
    toast.warning.mockReset()
  })

  it("shows the student's flagged question", () => {
    renderDialog()
    expect(screen.getByText("Does the hostel have AC rooms?")).toBeInTheDocument()
  })

  it("sends the reply with no expiry by default, then confirms and closes", async () => {
    mockMutateAsync.mockResolvedValue({})
    const user = userEvent.setup()
    const { onOpenChange } = renderDialog()

    await user.type(screen.getByLabelText(/your reply/i), "Yes, every hostel room has AC.")
    await user.click(screen.getByRole("button", { name: /send reply/i }))

    expect(mockMutateAsync).toHaveBeenCalledWith({
      queryId: 55,
      replyMessage: "Yes, every hostel room has AC.",
      expiresAt: null,
      additionalQueryIds: [],
    })
    expect(toast.success).toHaveBeenCalledWith("Reply sent to student.")
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("warns instead of a plain success toast when saving as a reusable answer fails", async () => {
    // The reply can still succeed (student got their answer) even if the
    // best-effort "teach the database" step behind it fails - staff need
    // to see that distinction, not a generic success toast.
    mockMutateAsync.mockResolvedValue({
      save_error: "Reply was sent, but saving it for future students failed. You can re-save it from the student's conversation.",
    })
    const user = userEvent.setup()
    const { onOpenChange } = renderDialog()

    await user.type(screen.getByLabelText(/your reply/i), "Yes, every hostel room has AC.")
    await user.click(screen.getByRole("button", { name: /send reply/i }))

    expect(toast.warning).toHaveBeenCalledWith(
      "Reply sent, but it wasn't saved for future students.",
      expect.objectContaining({
        description: "Reply was sent, but saving it for future students failed. You can re-save it from the student's conversation.",
      })
    )
    expect(toast.success).not.toHaveBeenCalled()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("includes an ISO expiry when the staff member opts into one", async () => {
    mockMutateAsync.mockResolvedValue({})
    const user = userEvent.setup()
    renderDialog()

    await user.type(screen.getByLabelText(/your reply/i), "This offer ends soon.")
    await user.click(screen.getByRole("checkbox", { name: /stop using this answer/i }))

    const dateInput = screen.getByDisplayValue(/\d{4}-\d{2}-\d{2}/)
    await user.click(screen.getByRole("button", { name: /send reply/i }))

    const call = mockMutateAsync.mock.calls[0][0]
    expect(call.queryId).toBe(55)
    expect(call.expiresAt).toBe(new Date(dateInput.value).toISOString())
  })

  it("shows an inline error and leaves the dialog open when the send fails", async () => {
    mockMutateAsync.mockRejectedValue(new Error("boom"))
    mockMutationState = { isPending: false, isError: true, error: { message: "Failed to send reply. Please try again." } }
    const user = userEvent.setup()
    const { onOpenChange } = renderDialog()

    await user.type(screen.getByLabelText(/your reply/i), "Trying to reply")
    await user.click(screen.getByRole("button", { name: /send reply/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to send reply. Please try again.")
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it("disables the submit button while the reply is sending", () => {
    mockMutationState = { isPending: true, isError: false, error: null }
    renderDialog()
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled()
  })

  it("fills the reply box from a draft-assist suggestion", async () => {
    mockSuggestionsState = {
      isLoading: false,
      data: {
        suggestions: [
          { chunk_id: 1, source_label: "Staff answer", content: "Question: x\nAnswer: Yes, all rooms have AC.", answer_text: "Yes, all rooms have AC.", distance: 0.05 },
        ],
      },
    }
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole("button", { name: /use this/i }))

    expect(screen.getByLabelText(/your reply/i)).toHaveValue("Yes, all rooms have AC.")
  })

  it("resolves the whole similar-question group with one reply", async () => {
    mockMutateAsync.mockResolvedValue({})
    const user = userEvent.setup()
    const similarGroup = [
      QUERY,
      { query_id: 56, student_id: 102, question_content: "Do hostel rooms come with AC?" },
      { query_id: 57, student_id: 103, question_content: "Is AC available in the hostel?" },
    ]
    renderDialog({ similarGroup })

    expect(screen.getByText(/2 other students asked basically the same thing/i)).toBeInTheDocument()

    await user.type(screen.getByLabelText(/your reply/i), "Yes, every hostel room has AC.")
    await user.click(screen.getByRole("button", { name: /send reply to 3 students/i }))

    expect(mockMutateAsync).toHaveBeenCalledWith({
      queryId: 55,
      replyMessage: "Yes, every hostel room has AC.",
      expiresAt: null,
      additionalQueryIds: [56, 57],
    })
    expect(toast.success).toHaveBeenCalledWith("Reply sent to 3 students.")
  })
})
