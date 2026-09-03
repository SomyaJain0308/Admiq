import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useStaffList(collegeId) {
  return useQuery({
    queryKey: ["staff", collegeId],
    queryFn: async () => {
      try {
        return await api.get(`/router/staff/${collegeId}`)
      } catch (err) {
        // 404 here means "no staff yet" (shouldn't really happen since the
        // caller themselves is staff, but handle it the same way as the
        // queue's empty state rather than showing a scary error).
        if (err instanceof ApiError && err.status === 404) {
          return []
        }
        throw err
      }
    },
    enabled: !!collegeId,
  })
}

export function useCreateStaff(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (staffData) => api.post(`/router/staff/${collegeId}`, staffData),
    onSuccess: () => {
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
      const previous = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old) => (old || []).filter((s) => s.staff_id !== staffId))
      return { previous, queryKey }
    },
    onError: (_err, _vars, context) => {
      if (context) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["staff", collegeId] })
    },
  })
}
