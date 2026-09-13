import { useQuery } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

// A college that hasn't been onboarded onto WhatsApp yet gets a 404 from
// this endpoint - that's an expected, common state (see the "ops-only"
// note on the backend route), not a failure. We catch it here and resolve
// to `null` instead, so callers can just check `data` rather than also
// juggling `isError`/`error.status` themselves.
export function useWhatsAppNumber(collegeId) {
  return useQuery({
    queryKey: ["whatsapp-number", collegeId],
    queryFn: async () => {
      try {
        return await api.get(`/router/college/${collegeId}/whatsapp-number`)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null
        }
        throw err
      }
    },
    enabled: !!collegeId,
  })
}
