import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import StudentsList from "@/pages/StudentsList"

const mockNavigate = vi.fn()

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom")
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockUseCurrentCollege = vi.fn()
vi.mock("@/context/useCurrentCollege", () => ({
  useCurrentCollege: () => mockUseCurrentCollege(),
}))

const mockUseAuth = vi.fn()
vi.mock("@/context/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}))

const mockUseStudentList = vi.fn()
const mockExportStudents = vi.fn()
vi.mock("@/hooks/useStudents", () => ({
  useStudentList: (...args) => mockUseStudentList(...args),
  exportStudents: (...args) => mockExportStudents(...args),
}))

const mockUseStaffList = vi.fn()
vi.mock("@/hooks/useStaff", () => ({
  useStaffList: () => mockUseStaffList(),
}))

const COLLEGE = { college_id: 1, college_name: "Delhi Public College" }
const STAFF_USER = { staff_id: 9 }

const STUDENTS = [
  {
    student_id: 101,
    student_name: "Aisha Khan",
    student_phone: "+91 90000 00001",
    course_interest: "B.Tech CSE",
    lead_score: 82,
    profile_signals: { concerns: ["fee worry"] },
  },
  {
    student_id: 102,
    student_name: "Rohan Verma",
    student_phone: "+91 90000 00002",
    course_interest: "BBA",
    lead_score: 25,
    profile_signals: { concerns: [] },
  },
]

function renderPage() {
  return render(
    <MemoryRouter>
      <StudentsList />
    </MemoryRouter>
  )
}

describe("StudentsList", () => {
  beforeEach(() => {
    mockNavigate.mockReset()
    mockExportStudents.mockReset().mockResolvedValue(undefined)
    mockUseCurrentCollege.mockReturnValue({ college: COLLEGE, hasNoCollege: false })
    mockUseAuth.mockReturnValue({ user: STAFF_USER })
    mockUseStaffList.mockReturnValue({ data: { items: [] } })
    mockUseStudentList.mockReturnValue({
      data: { items: STUDENTS, total: STUDENTS.length },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    })
  })

  it("shows the no-college empty state instead of the table when the staff member has no college", () => {
    mockUseCurrentCollege.mockReturnValue({ college: null, hasNoCollege: true })
    renderPage()
    expect(screen.getByText("No college access yet")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("renders each student with their lead score band and concern badge", () => {
    renderPage()
    expect(screen.getByText("Aisha Khan")).toBeInTheDocument()
    expect(screen.getByText("82 · Hot")).toBeInTheDocument()
    expect(screen.getByText("1 concern")).toBeInTheDocument()

    expect(screen.getByText("Rohan Verma")).toBeInTheDocument()
    expect(screen.getByText("25 · Cold")).toBeInTheDocument()
  })

  it("shows the empty state when there are no students and no filters applied", () => {
    mockUseStudentList.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    })
    renderPage()
    expect(screen.getByText("No students yet")).toBeInTheDocument()
  })

  it("shows the load error message when the query fails", () => {
    mockUseStudentList.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      isError: true,
      error: { message: "Network error" },
    })
    renderPage()
    expect(screen.getByRole("alert")).toHaveTextContent("Network error")
  })

  it("navigates to the student detail page when a row is clicked", async () => {
    const user = userEvent.setup()
    renderPage()
    // Click a cell that isn't the name <Link> itself - the row's own
    // onClick handler explicitly skips navigating when the click landed on
    // the link (to avoid double-navigating), so this is what exercises it.
    await user.click(screen.getByText("+91 90000 00001"))
    expect(mockNavigate).toHaveBeenCalledWith("/students/101")
  })

  it("exports the current student list to CSV", async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByTitle("Export to CSV"))
    expect(mockExportStudents).toHaveBeenCalledWith(COLLEGE.college_id, "")
  })
})
