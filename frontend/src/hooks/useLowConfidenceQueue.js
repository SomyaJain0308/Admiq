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
    // additionalQueryIds is likewise optional - it's how a "similar open
    // questions" group gets resolved by the same reply in one request
    // instead of one request per query.
    mutationFn: ({ queryId, replyMessage, expiresAt, additionalQueryIds }) => {
      const params = { reply_message: replyMessage }
      if (expiresAt) params.expires_at = expiresAt
      if (additionalQueryIds?.length) params.additional_query_ids = additionalQueryIds
      return api.postWithQueryParams(`/router/low_confidence/${collegeId}/query/${queryId}/reply`, params)
    },
    // Optimistic update: remove the query (and any bundled similar queries)
    // from the open list immediately, rather than waiting for the round
    // trip - replying feels instant. If the request actually fails, roll
    // the cache back to what it was before. Prefix-matches every cached
    // page of the open (resolved=false) queue, since the reply could've
    // come from any page currently in cache.
    onMutate: async ({ queryId, additionalQueryIds }) => {
      const resolvedIds = new Set([queryId, ...(additionalQueryIds || [])])
      const queryKey = ["low-confidence-queries", collegeId, false]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueriesData({ queryKey })
      queryClient.setQueriesData({ queryKey }, (old) => {
        if (!old?.items) return old
        const removed = old.items.filter((q) => resolvedIds.has(q.query_id)).length
        return { ...old, items: old.items.filter((q) => !resolvedIds.has(q.query_id)), total: Math.max(0, old.total - removed) }
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
      queryClient.invalidateQueries({ queryKey: ["low-confidence-similar-groups", collegeId] })
    },
  })
}

// Draft-assist: the closest existing knowledge-base matches for this
// specific flagged question, so staff see what's already known before
// typing a reply from scratch. Only fetched while a query is actually
// loaded (the dialog passes enabled: false until then).
export function useReplySuggestions(collegeId, queryId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ["low-confidence-suggestions", collegeId, queryId],
    queryFn: () => api.get(`/router/low_confidence/${collegeId}/query/${queryId}/suggestions`),
    enabled: !!collegeId && !!queryId && enabled,
    staleTime: 60_000,
  })
}

// Free-text search over the whole knowledge base (documents + past staff
// answers), so staff can check what's already on record while composing a
// reply instead of risking a contradiction. The dialog only enables this
// once the staff member has actually typed something to search for.
export function useKnowledgeSearch(collegeId, searchTerm, { enabled = true } = {}) {
  const trimmed = (searchTerm || "").trim()
  return useQuery({
    queryKey: ["low-confidence-knowledge-search", collegeId, trimmed],
    queryFn: () => api.get(`/router/low_confidence/${collegeId}/knowledge-search?q=${encodeURIComponent(trimmed)}`),
    enabled: !!collegeId && trimmed.length >= 2 && enabled,
    staleTime: 30_000,
  })
}

// Clusters of currently-open questions that look like the same underlying
// question in different words, so staff can spot "N students asked this"
// and answer the whole group at once (see additionalQueryIds above) instead
// of retyping the same reply repeatedly.
export function useSimilarQueryGroups(collegeId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ["low-confidence-similar-groups", collegeId],
    queryFn: () => api.get(`/router/low_confidence/${collegeId}/similar-groups`),
    enabled: !!collegeId && enabled,
    // Same "live support inbox" reasoning as the open queue itself - a
    // fresh cluster can form the moment a second student asks the same
    // thing, and staff shouldn't have to leave and come back to see it.
    refetchInterval: 30_000,
  })
}
