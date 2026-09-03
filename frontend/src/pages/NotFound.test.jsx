import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import NotFound from "@/pages/NotFound"

describe("NotFound", () => {
  it("renders a 404 message and a link back to the dashboard", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>
    )
    expect(screen.getByText("404")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toHaveAttribute("href", "/")
  })
})
