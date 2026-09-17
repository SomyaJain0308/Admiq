import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useKnowledgeConflicts(collegeId, status = "open", { page = 1, pageSize = 20 } = {}) {
  return useQuery({
    queryKey: ["knowledge-conflicts", collegeId, status, page, pageSize],
    queryFn: () => api.get(`/router/colleges/${collegeId}/knowledge-conflicts?status=${status}&page=${page}&page_size=${pageSize}`),
    enabled: !!collegeId,
    placeholderData: keepPreviousData,
    // A conflict can get flagged the moment staff save a reply or upload a
    // document, so the open queue polls like a live inbox (same interval as
    // the low-confidence queue). Reviewed history changes less urgently.
    refetchInterval: status === "open" ? 15_000 : 60_000,
  })
}

function useReviewConflict(collegeId, action) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (conflictId) => api.post(`/router/colleges/${collegeId}/knowledge-conflicts/${conflictId}/${action}`),
    // Optimistic update: remove the conflict from the open list immediately
    // rather than waiting for the round trip, same pattern as resolving a
    // low-confidence query. Prefix-matches every cached page of the open
    // list, since the conflict could've come from any page in cache.
    onMutate: async (conflictId) => {
      const queryKey = ["knowledge-conflicts", collegeId, "open"]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueriesData({ queryKey })
      queryClient.setQueriesData({ queryKey }, (old) => {
        if (!old?.items) return old
        return { ...old, items: old.items.filter((c) => c.conflict_id !== conflictId), total: Math.max(0, old.total - 1) }
      })
      return { previous }
    },
    onError: (_err, _vars, context) => {
      context?.previous?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data)
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge-conflicts", collegeId] })
    },
  })
}

export function useResolveConflict(collegeId) {
  return useReviewConflict(collegeId, "resolve")
}

export function useDismissConflict(collegeId) {
  return useReviewConflict(collegeId, "dismiss")
}
