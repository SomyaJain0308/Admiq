import React from "react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { renderHook, waitFor, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api")
  return {
    ...actual,
    api: {
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      postWithQueryParams: vi.fn(),
    },
  }
})

import { api } from "@/lib/api"
import { useResolveLowConfidenceQuery } from "@/hooks/useLowConfidenceQueue"

const COLLEGE_ID = 3
// Two cached "pages" of the open (resolved=false) queue - mirrors what's
// actually in cache once a staff member has paged past page 1.
const PAGE_1_KEY = ["low-confidence-queries", COLLEGE_ID, false, 1, 20]
const PAGE_2_KEY = ["low-confidence-queries", COLLEGE_ID, false, 2, 20]

const page1Data = { items: [{ query_id: 1 }, { query_id: 2 }], total: 5 }
const page2Data = { items: [{ query_id: 21 }], total: 5 }

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  function Wrapper({ children }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
  return { Wrapper, queryClient }
}

function seedPages(queryClient) {
  queryClient.setQueryData(PAGE_1_KEY, page1Data)
  queryClient.setQueryData(PAGE_2_KEY, page2Data)
}

beforeEach(() => {
  api.postWithQueryParams.mockReset()
})

describe("useResolveLowConfidenceQuery", () => {
  it("removes the resolved query from whichever cached page holds it, and decrements total everywhere", async () => {
    let resolveRequest
    api.postWithQueryParams.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve
      })
    )
    const { Wrapper, queryClient } = createWrapper()
    seedPages(queryClient)

    const { result } = renderHook(() => useResolveLowConfidenceQuery(COLLEGE_ID), { wrapper: Wrapper })

    act(() => {
      result.current.mutate({ queryId: 1, replyMessage: "It's on our website." })
    })

    // Query 1 lived on page 1 - it should disappear from there, and total
    // (a global count shared across every cached page view) should drop on
    // both pages even though page 2's own items list didn't contain it.
    await waitFor(() => {
      expect(queryClient.getQueryData(PAGE_1_KEY)).toEqual({ items: [{ query_id: 2 }], total: 4 })
    })
    expect(queryClient.getQueryData(PAGE_2_KEY)).toEqual({ items: [{ query_id: 21 }], total: 4 })

    resolveRequest({})
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("restores every cached page to its pre-optimistic state if the reply fails to send", async () => {
    api.postWithQueryParams.mockRejectedValue(new Error("network error"))
    const { Wrapper, queryClient } = createWrapper()
    seedPages(queryClient)

    const { result } = renderHook(() => useResolveLowConfidenceQuery(COLLEGE_ID), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ queryId: 1, replyMessage: "It's on our website." }).catch(() => {})
    })

    expect(result.current.isError).toBe(true)
    expect(queryClient.getQueryData(PAGE_1_KEY)).toEqual(page1Data)
    expect(queryClient.getQueryData(PAGE_2_KEY)).toEqual(page2Data)
  })

  it("only sends expires_at when an expiry was actually chosen", async () => {
    api.postWithQueryParams.mockResolvedValue({})
    const { Wrapper, queryClient } = createWrapper()
    seedPages(queryClient)

    const { result } = renderHook(() => useResolveLowConfidenceQuery(COLLEGE_ID), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ queryId: 2, replyMessage: "No expiry here" })
    })

    expect(api.postWithQueryParams).toHaveBeenCalledWith(
      `/router/low_confidence/${COLLEGE_ID}/query/2/reply`,
      { reply_message: "No expiry here" }
    )
  })
})
