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
      downloadFile: vi.fn(),
    },
  }
})

import { api } from "@/lib/api"
import { useDeleteStaff, exportStaff } from "@/hooks/useStaff"

const COLLEGE_ID = 9
// Two cached variants that legitimately coexist: an unfiltered page 1, and a
// search-filtered result that happens to include the same staff member.
const ALL_KEY = ["staff", COLLEGE_ID, 1, 20, ""]
const SEARCH_KEY = ["staff", COLLEGE_ID, 1, 20, "priya"]

const allData = { items: [{ staff_id: 1, staff_name: "Priya" }, { staff_id: 2, staff_name: "Sam" }], total: 8 }
const searchData = { items: [{ staff_id: 1, staff_name: "Priya" }], total: 1 }

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
  queryClient.setQueryData(ALL_KEY, allData)
  queryClient.setQueryData(SEARCH_KEY, searchData)
}

beforeEach(() => {
  api.delete.mockReset()
  api.downloadFile.mockReset()
})

describe("useDeleteStaff", () => {
  it("removes the staff member from every cached page/search variant at once", async () => {
    let resolveRequest
    api.delete.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve
      })
    )
    const { Wrapper, queryClient } = createWrapper()
    seedPages(queryClient)

    const { result } = renderHook(() => useDeleteStaff(COLLEGE_ID), { wrapper: Wrapper })

    act(() => {
      result.current.mutate(1)
    })

    await waitFor(() => {
      expect(queryClient.getQueryData(ALL_KEY)).toEqual({ items: [{ staff_id: 2, staff_name: "Sam" }], total: 7 })
    })
    // The search-filtered view had nothing left once its one match is gone.
    expect(queryClient.getQueryData(SEARCH_KEY)).toEqual({ items: [], total: 0 })

    resolveRequest({})
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it("restores every cached variant if the delete request fails", async () => {
    api.delete.mockRejectedValue(new Error("network error"))
    const { Wrapper, queryClient } = createWrapper()
    seedPages(queryClient)

    const { result } = renderHook(() => useDeleteStaff(COLLEGE_ID), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync(1).catch(() => {})
    })

    expect(result.current.isError).toBe(true)
    expect(queryClient.getQueryData(ALL_KEY)).toEqual(allData)
    expect(queryClient.getQueryData(SEARCH_KEY)).toEqual(searchData)
  })
})

describe("exportStaff", () => {
  it("hits the export endpoint with no query string when there's no search term", () => {
    exportStaff(COLLEGE_ID)
    expect(api.downloadFile).toHaveBeenCalledWith(`/router/staff/${COLLEGE_ID}/export`)
  })

  it("includes the search term as a query param when one is given", () => {
    exportStaff(COLLEGE_ID, "priya")
    expect(api.downloadFile).toHaveBeenCalledWith(`/router/staff/${COLLEGE_ID}/export?search=priya`)
  })
})
