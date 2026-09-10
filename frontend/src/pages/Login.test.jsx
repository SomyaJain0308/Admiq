import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import Login from "@/pages/Login"
import { ApiError } from "@/lib/api"

const mockNavigate = vi.fn()
const mockLogin = vi.fn()

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom")
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ login: mockLogin }),
}))

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

describe("Login", () => {
  beforeEach(() => {
    mockNavigate.mockReset()
    mockLogin.mockReset()
  })

  it("logs in and redirects to the dashboard on success", async () => {
    const user = userEvent.setup()
    mockLogin.mockResolvedValue(undefined)
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), "staff@college.edu")
    await user.type(screen.getByLabelText(/password/i), "correct-password")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("staff@college.edu", "correct-password")
    })
    expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true })
  })

  it("shows an incorrect-credentials message on a 401", async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new ApiError("Incorrect email or password", 401, null))
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), "staff@college.edu")
    await user.type(screen.getByLabelText(/password/i), "wrong-password")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.")
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it("shows a rate-limit message on a 429", async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new ApiError("Too many requests", 429, null))
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), "staff@college.edu")
    await user.type(screen.getByLabelText(/password/i), "correct-password")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Please wait a minute and try again.")
  })

  it("shows a generic message for anything else and re-enables the form", async () => {
    const user = userEvent.setup()
    mockLogin.mockRejectedValue(new Error("network down"))
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), "staff@college.edu")
    await user.type(screen.getByLabelText(/password/i), "correct-password")
    const submitButton = screen.getByRole("button", { name: /sign in/i })
    await user.click(submitButton)

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Please try again.")
    expect(submitButton).not.toBeDisabled()
  })

  it("redirects back to the page that required login instead of the dashboard", async () => {
    mockLogin.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={[{ pathname: "/login", state: { from: { pathname: "/students" } } }]}>
        <Login />
      </MemoryRouter>
    )

    await user.type(screen.getByLabelText(/email/i), "staff@college.edu")
    await user.type(screen.getByLabelText(/password/i), "correct-password")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/students", { replace: true })
    })
  })
})
