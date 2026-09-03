import { describe, it, expect, vi, afterEach } from "vitest"
import { timeSince } from "@/lib/formatTime"

describe("timeSince", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("returns 'just now' for timestamps under a minute old", () => {
    const now = new Date("2026-01-01T12:00:00Z")
    vi.useFakeTimers().setSystemTime(now)
    expect(timeSince(new Date("2026-01-01T11:59:30Z").toISOString())).toBe("just now")
  })

  it("formats minutes correctly", () => {
    const now = new Date("2026-01-01T12:00:00Z")
    vi.useFakeTimers().setSystemTime(now)
    expect(timeSince(new Date("2026-01-01T11:45:00Z").toISOString())).toBe("15m")
  })

  it("formats hours correctly", () => {
    const now = new Date("2026-01-01T12:00:00Z")
    vi.useFakeTimers().setSystemTime(now)
    expect(timeSince(new Date("2026-01-01T09:00:00Z").toISOString())).toBe("3h")
  })

  it("formats days correctly", () => {
    const now = new Date("2026-01-05T12:00:00Z")
    vi.useFakeTimers().setSystemTime(now)
    expect(timeSince(new Date("2026-01-01T12:00:00Z").toISOString())).toBe("4d")
  })

  it("returns an empty string for a missing timestamp", () => {
    expect(timeSince(null)).toBe("")
    expect(timeSince(undefined)).toBe("")
  })
})
