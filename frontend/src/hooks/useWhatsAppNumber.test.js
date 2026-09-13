import React from "react"
import { describe, it, expect, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
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
import { useWhatsAppNumber } from "@/hooks/useWhatsAppNumber"

const COLLEGE_ID = 9

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children)
  }
  return Wrapper
}

describe("useWhatsAppNumber", () => {
  it("returns the connected number on success", async () => {
    const number = { number_id: 1, college_id: COLLEGE_ID, display_number: "+917000000000" }
    api.get.mockResolvedValueOnce(number)

    const { result } = renderHook(() => useWhatsAppNumber(COLLEGE_ID), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(number)
    expect(api.get).toHaveBeenCalledWith(`/router/college/${COLLEGE_ID}/whatsapp-number`)
  })

  it("resolves to null (not an error) when no number is connected yet", async () => {
    api.get.mockRejectedValueOnce(new ApiError("No WhatsApp number is connected for this college yet", 404, null))

    const { result } = renderHook(() => useWhatsAppNumber(COLLEGE_ID), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })

  it("surfaces non-404 errors as real query errors", async () => {
    api.get.mockRejectedValueOnce(new ApiError("Server error", 500, null))

    const { result } = renderHook(() => useWhatsAppNumber(COLLEGE_ID), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it("does not fetch when no collegeId is provided", () => {
    const { result } = renderHook(() => useWhatsAppNumber(undefined), { wrapper: createWrapper() })

    expect(result.current.fetchStatus).toBe("idle")
    expect(api.get).not.toHaveBeenCalled()
  })
})
