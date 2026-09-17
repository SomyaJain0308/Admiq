import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useKnowledgeBase(collegeId, { search = "", expiringSoon = false, unused = false, page = 1, pageSize = 20 } = {}) {
  return useQuery({
    queryKey: ["knowledge-base", collegeId, search, expiringSoon, unused, page, pageSize],
    queryFn: () => {
      const params = new URLSearchParams({ page, page_size: pageSize })
      if (search) params.set("search", search)
      if (expiringSoon) params.set("expiring_soon", "true")
      if (unused) params.set("unused", "true")
      return api.get(`/router/colleges/${collegeId}/knowledge-base?${params.toString()}`)
    },
    enabled: !!collegeId,
    placeholderData: keepPreviousData,
  })
}

export function useCreateKnowledgeBaseEntry(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (entry) => api.post(`/router/colleges/${collegeId}/knowledge-base`, entry),
    onSuccess: () => {
      // Prefix match (no search/filter/page in this key) invalidates every
      // cached page/filter variant for this college, not just one.
      queryClient.invalidateQueries({ queryKey: ["knowledge-base", collegeId] })
    },
  })
}

export function useUpdateKnowledgeBaseEntry(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ chunkId, updates }) => api.patch(`/router/colleges/${collegeId}/knowledge-base/${chunkId}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge-base", collegeId] })
    },
  })
}

export function useDeleteKnowledgeBaseEntry(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (chunkId) => api.delete(`/router/colleges/${collegeId}/knowledge-base/${chunkId}`),
    onMutate: async (chunkId) => {
      const queryKey = ["knowledge-base", collegeId]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueriesData({ queryKey })
      // Optimistically drop the row from every cached page/filter variant -
      // deleting an entry should feel instant, same as document delete.
      queryClient.setQueriesData({ queryKey }, (old) => {
        if (!old?.items) return old
        const removed = old.items.filter((e) => e.chunk_id === chunkId).length
        return { ...old, items: old.items.filter((e) => e.chunk_id !== chunkId), total: Math.max(0, old.total - removed) }
      })
      return { previous }
    },
    onError: (_err, _vars, context) => {
      context?.previous?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data)
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge-base", collegeId] })
    },
  })
}
