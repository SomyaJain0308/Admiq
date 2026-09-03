import { describe, it, expect, vi, beforeEach } from "vitest"

// Mock the token store so we control exactly what tokens are "stored"
// without touching real localStorage.
vi.mock("@/lib/tokenStore", () => {
  let access = "expired-access-token"
  let refresh = "valid-refresh-token"
  return {
    getAccessToken: () => access,
    setAccessToken: (t) => {
      access = t
    },
    getRefreshToken: () => refresh,
    setRefreshToken: (t) => {
      refresh = t
    },
    clearTokens: () => {
      access = null
      refresh = null
    },
  }
})

describe("api - concurrent 401 refresh deduplication", () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it("only calls /refresh once when two requests hit 401 at the same time", async () => {
    let refreshCallCount = 0

    global.fetch = vi.fn(async (url, options) => {
      if (url.toString().endsWith("/refresh")) {
        refreshCallCount++
        // Simulate real network latency, so both 401'd requests are actually
        // waiting on this same call at the same time, not sequentially.
        await new Promise((resolve) => setTimeout(resolve, 20))
        return {
          ok: true,
          status: 200,
          json: async () => ({ access_token: "new-access-token", refresh_token: "new-refresh-token" }),
        }
      }
      // Any other endpoint: fail with 401 the first time it's called with the
      // stale token, succeed once the retry carries the new one.
      const authHeader = options?.headers?.["Authorization"]
      if (authHeader === "Bearer new-access-token") {
        return { ok: true, status: 200, json: async () => ({ ok: true }) }
      }
      return { ok: false, status: 401, json: async () => ({ detail: "expired" }) }
    })

    const { api } = await import("@/lib/api")

    // Fire two authenticated requests "at the same time" - both should hit
    // the 401 branch and both need a refresh, but only one real /refresh
    // call should go out.
    const [resultA, resultB] = await Promise.all([api.get("/router/students/1"), api.get("/router/staff/1")])

    expect(resultA).toEqual({ ok: true })
    expect(resultB).toEqual({ ok: true })
    expect(refreshCallCount).toBe(1)
  })
})
