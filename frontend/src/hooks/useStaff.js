import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useStaffList(collegeId, { page = 1, pageSize = 20, search = "" } = {}) {
  return useQuery({
    queryKey: ["staff", collegeId, page, pageSize, search],
    queryFn: () => {
      const params = new URLSearchParams({ page, page_size: pageSize })
      if (search) params.set("search", search)
      return api.get(`/router/staff/${collegeId}?${params.toString()}`)
    },
    enabled: !!collegeId,
    placeholderData: keepPreviousData,
  })
}

export function useCreateStaff(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (staffData) => api.post(`/router/staff/${collegeId}`, staffData),
    onSuccess: () => {
      // Prefix match (no page/pageSize/search in this key) invalidates every
      // cached page/search variant for this college, not just one.
      queryClient.invalidateQueries({ queryKey: ["staff", collegeId] })
    },
  })
}

export function useUpdateStaff(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ staffId, updates }) => api.patch(`/router/staff/${collegeId}/${staffId}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff", collegeId] })
    },
  })
}

export function useDeleteStaff(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (staffId) => api.delete(`/router/staff/${collegeId}/${staffId}`),
    onMutate: async (staffId) => {
      const queryKey = ["staff", collegeId]
      await queryClient.cancelQueries({ queryKey })
      // Snapshot every cached page/search variant so onError can restore all
      // of them, not just whichever one happened to be active.
      const previous = queryClient.getQueriesData({ queryKey })
      queryClient.setQueriesData({ queryKey }, (old) => {
        if (!old?.items) return old
        return { ...old, items: old.items.filter((s) => s.staff_id !== staffId), total: Math.max(0, old.total - 1) }
      })
      return { previous }
    },
    onError: (_err, _vars, context) => {
      context?.previous?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data)
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["staff", collegeId] })
    },
  })
}

export function exportStaff(collegeId, search = "") {
  const params = new URLSearchParams()
  if (search) params.set("search", search)
  const query = params.toString()
  return api.downloadFile(`/router/staff/${collegeId}/export${query ? `?${query}` : ""}`)
}
