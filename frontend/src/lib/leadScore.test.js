import { describe, it, expect } from "vitest"
import { leadScoreBand } from "@/lib/leadScore"

describe("leadScoreBand", () => {
  it("classifies scores below 40 as Cold", () => {
    expect(leadScoreBand(0).label).toBe("Cold")
    expect(leadScoreBand(39).label).toBe("Cold")
  })

  it("classifies scores 40-69 as Warm", () => {
    expect(leadScoreBand(40).label).toBe("Warm")
    expect(leadScoreBand(69).label).toBe("Warm")
  })

  it("classifies scores 70 and above as Hot", () => {
    expect(leadScoreBand(70).label).toBe("Hot")
    expect(leadScoreBand(100).label).toBe("Hot")
  })
})
