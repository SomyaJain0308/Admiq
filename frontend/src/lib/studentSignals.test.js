import { describe, it, expect } from "vitest"
import { getSignalChips } from "@/lib/studentSignals"

describe("getSignalChips", () => {
  it("returns no chips for null profile_signals (nullable JSONB column)", () => {
    expect(getSignalChips(null)).toEqual([])
  })

  it("returns no chips for undefined profile_signals", () => {
    expect(getSignalChips(undefined)).toEqual([])
  })

  it("returns no chips when called with no argument", () => {
    expect(getSignalChips()).toEqual([])
  })

  it("returns no chips for an empty signals object", () => {
    expect(getSignalChips({})).toEqual([])
  })

  it("includes an at-risk chip when dropoff_reason is set", () => {
    const chips = getSignalChips({ dropoff_reason: "Stopped responding after fee question" })
    expect(chips.map((c) => c.key)).toContain("dropoff")
  })

  it("includes a concerns chip with a count when concerns exist", () => {
    const chips = getSignalChips({ concerns: ["Fee worries", "Hostel availability"] })
    const concernChip = chips.find((c) => c.key === "concerns")
    expect(concernChip.label).toBe("2 concerns")
  })

  it("orders chips with dropoff risk first", () => {
    const chips = getSignalChips({
      dropoff_reason: "Went quiet",
      concerns: ["Fees"],
      competing_colleges: ["Other College"],
      guardian_involvement: "Parent asked about scholarships",
    })
    expect(chips.map((c) => c.key)).toEqual(["dropoff", "concerns", "competing", "guardian"])
  })
})
