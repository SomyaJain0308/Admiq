import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useLowConfidenceQueries(collegeId, resolved = false) {
  return useQuery({
    queryKey: ["low-confidence-queries", collegeId, resolved],
    queryFn: async () => {
      try {
        return await api.get(`/router/low_confidence/${collegeId}?resolved=${resolved}`)
      } catch (err) {
        // The backend returns a 404 when there are none matching, rather
        // than an empty array - that's a real, expected state here.
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
    // Optimistic update: remove the query from the open list immediately,
    // rather than waiting for the round trip - replying feels instant. If the
    // request actually fails, roll the cache back to what it was before.
    onMutate: async ({ queryId }) => {
      const queryKey = ["low-confidence-queries", collegeId, false]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old) => (old || []).filter((q) => q.query_id !== queryId))
      return { previous, queryKey }
    },
    onError: (_err, _vars, context) => {
      if (context) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["low-confidence-queries", collegeId] })
    },
  })
}
