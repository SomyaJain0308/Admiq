import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { toast } from "sonner"
import { WhatsAppWidgetCard } from "@/components/WhatsAppWidgetCard"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

let mockQueryState = { data: null, isLoading: false }
vi.mock("@/hooks/useWhatsAppNumber", () => ({
  useWhatsAppNumber: () => mockQueryState,
}))

function renderCard() {
  return render(
    <MemoryRouter>
      <WhatsAppWidgetCard collegeId={1} />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockQueryState = { data: null, isLoading: false }
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
})

describe("WhatsAppWidgetCard", () => {
  it("shows a loading state while the connection check is in flight", () => {
    mockQueryState = { data: undefined, isLoading: true }
    renderCard()

    expect(screen.getByText(/checking your whatsapp connection/i)).toBeInTheDocument()
  })

  it("points staff to Support when no number is connected yet", () => {
    mockQueryState = { data: null, isLoading: false }
    renderCard()

    expect(screen.getByText(/no whatsapp number is connected/i)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /support/i })).toHaveAttribute("href", "/support")
    expect(screen.queryByRole("button", { name: /copy website code/i })).not.toBeInTheDocument()
  })

  it("shows the preview and connected number, and copies the embed snippet with the real number baked in", async () => {
    const user = userEvent.setup()
    mockQueryState = { data: { display_number: "+91 70000 00000" }, isLoading: false }
    renderCard()

    expect(screen.getByText("+91 70000 00000")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /copy website code/i }))

    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1)
    const copiedCode = navigator.clipboard.writeText.mock.calls[0][0]
    expect(copiedCode).toContain("917000000000") // digits-only, stripped of "+" and spaces
    expect(copiedCode).toContain("Chat with Admiq")
    expect(copiedCode).not.toMatch(/college/i) // brand copy stays generic, no college name
    expect(toast.success).toHaveBeenCalled()
    expect(await screen.findByRole("button", { name: /^copied$/i })).toBeInTheDocument()
  })

  it("shows an error toast if the clipboard write fails", async () => {
    const user = userEvent.setup()
    navigator.clipboard.writeText.mockRejectedValueOnce(new Error("denied"))
    mockQueryState = { data: { display_number: "+917000000000" }, isLoading: false }
    renderCard()

    await user.click(screen.getByRole("button", { name: /copy website code/i }))

    expect(toast.error).toHaveBeenCalled()
  })
})
