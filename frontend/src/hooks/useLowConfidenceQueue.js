import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useLowConfidenceQueries(collegeId, resolved = false, { page = 1, pageSize = 20 } = {}) {
  return useQuery({
    queryKey: ["low-confidence-queries", collegeId, resolved, page, pageSize],
    queryFn: () => api.get(`/router/low_confidence/${collegeId}?resolved=${resolved}&page=${page}&page_size=${pageSize}`),
    enabled: !!collegeId,
    placeholderData: keepPreviousData,
    // This is a live support inbox, not a static report - a new question
    // can get flagged at any moment, and staff shouldn't have to switch
    // tabs away and back (the only thing that would otherwise trigger a
    // refetch) to find out. Resolved history changes less urgently, so it
    // polls slower.
    refetchInterval: resolved ? 60_000 : 15_000,
  })
}

export function useResolveLowConfidenceQuery(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    // expiresAt is optional now - "never expires" is a real, first-class
    // option (the backend treats a NULL expires_at as "always retrievable"),
    // not just a very-far-off date. Only include the param at all when one
    // was actually chosen - URLSearchParams would otherwise send it as the
    // literal string "null"/"undefined", which FastAPI can't parse as a date.
    mutationFn: ({ queryId, replyMessage, expiresAt }) => {
      const params = { reply_message: replyMessage }
      if (expiresAt) params.expires_at = expiresAt
      return api.postWithQueryParams(`/router/low_confidence/${collegeId}/query/${queryId}/reply`, params)
    },
    // Optimistic update: remove the query from the open list immediately,
    // rather than waiting for the round trip - replying feels instant. If the
    // request actually fails, roll the cache back to what it was before.
    // Prefix-matches every cached page of the open (resolved=false) queue,
    // since the reply could've come from any page currently in cache.
    onMutate: async ({ queryId }) => {
      const queryKey = ["low-confidence-queries", collegeId, false]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueriesData({ queryKey })
      queryClient.setQueriesData({ queryKey }, (old) => {
        if (!old?.items) return old
        return { ...old, items: old.items.filter((q) => q.query_id !== queryId), total: Math.max(0, old.total - 1) }
      })
      return { previous }
    },
    onError: (_err, _vars, context) => {
      context?.previous?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data)
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["low-confidence-queries", collegeId] })
    },
  })
}
