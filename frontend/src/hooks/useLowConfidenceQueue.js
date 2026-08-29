import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useLowConfidenceQueries(collegeId) {
  return useQuery({
    queryKey: ["low-confidence-queries", collegeId],
    queryFn: async () => {
      try {
        return await api.get(`/router/low_confidence/${collegeId}`)
      } catch (err) {
        // The backend returns a 404 when the queue is empty rather than an
        // empty array - that's a real, expected state here, not an error.
        if (err instanceof ApiError && err.status === 404) {
          return []
        }
        throw err
      }
    },
    enabled: !!collegeId,
  })
}

export function useResolveLowConfidenceQuery(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ queryId, replyMessage, expiresAt }) =>
      api.postWithQueryParams(`/router/low_confidence/${collegeId}/query/${queryId}/reply`, {
        reply_message: replyMessage,
        expires_at: expiresAt,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["low-confidence-queries", collegeId] })
    },
  })
}
