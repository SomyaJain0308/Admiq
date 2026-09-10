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
    },
  }
})

import { api, ApiError } from "@/lib/api"
import { useDocuments, useBulkDeleteDocuments } from "@/hooks/useDocuments"

const COLLEGE_ID = 7
const DOCS_KEY = ["documents", COLLEGE_ID]

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

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
})

describe("useDocuments", () => {
  it("returns the document list on success", async () => {
    api.get.mockResolvedValue([{ document_id: 1, file_name: "a.pdf", status: "success" }])
    const { Wrapper } = createWrapper()

    const { result } = renderHook(() => useDocuments(COLLEGE_ID), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([{ document_id: 1, file_name: "a.pdf", status: "success" }])
  })

  it("treats a 404 as 'no documents yet' rather than an error", async () => {
    api.get.mockRejectedValue(new ApiError("Not found", 404, null))
    const { Wrapper } = createWrapper()

    const { result } = renderHook(() => useDocuments(COLLEGE_ID), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it("propagates non-404 errors instead of swallowing them", async () => {
    api.get.mockRejectedValue(new ApiError("Server error", 500, null))
    const { Wrapper } = createWrapper()

    const { result } = renderHook(() => useDocuments(COLLEGE_ID), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error.status).toBe(500)
  })
})

describe("useBulkDeleteDocuments", () => {
  const initialDocs = [
    { document_id: 1, file_name: "one.pdf" },
    { document_id: 2, file_name: "two.pdf" },
    { document_id: 3, file_name: "three.pdf" },
  ]

  it("optimistically removes every selected document before the request resolves", async () => {
    let resolveRequest
    api.post.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve
      })
    )
    const { Wrapper, queryClient } = createWrapper()
    queryClient.setQueryData(DOCS_KEY, initialDocs)

    const { result } = renderHook(() => useBulkDeleteDocuments(COLLEGE_ID), { wrapper: Wrapper })

    act(() => {
      result.current.mutate([1, 3])
    })

    // Still in flight, but the cache should already reflect the optimistic
    // removal - this is what makes bulk delete feel instant.
    await waitFor(() => {
      expect(queryClient.getQueryData(DOCS_KEY)).toEqual([{ document_id: 2, file_name: "two.pdf" }])
    })

    resolveRequest({ deleted_ids: [1, 3], not_found_ids: [] })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("restores only the rows the server reports it couldn't delete", async () => {
    // Server actually only managed to delete document 1 - document 3 was
    // already gone (e.g. deleted by someone else a moment earlier).
    api.post.mockResolvedValue({ deleted_ids: [1], not_found_ids: [3] })
    const { Wrapper, queryClient } = createWrapper()
    queryClient.setQueryData(DOCS_KEY, initialDocs)

    const { result } = renderHook(() => useBulkDeleteDocuments(COLLEGE_ID), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync([1, 3])
    })

    const finalDocs = queryClient.getQueryData(DOCS_KEY)
    // Document 1 stays deleted, document 3 reappears, document 2 was never
    // touched - a partial failure shouldn't make a successfully-deleted row
    // come back, or leave a not-actually-deleted row missing.
    expect(finalDocs.map((d) => d.document_id).sort()).toEqual([2, 3])
  })

  it("rolls every optimistically-removed row back on a total failure", async () => {
    api.post.mockRejectedValue(new Error("network error"))
    const { Wrapper, queryClient } = createWrapper()
    queryClient.setQueryData(DOCS_KEY, initialDocs)

    const { result } = renderHook(() => useBulkDeleteDocuments(COLLEGE_ID), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync([1, 3]).catch(() => {})
    })

    expect(result.current.isError).toBe(true)
    expect(queryClient.getQueryData(DOCS_KEY)).toEqual(initialDocs)
  })
})
