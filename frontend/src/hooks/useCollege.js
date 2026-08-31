import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useCollegeDetail(collegeId) {
  return useQuery({
    queryKey: ["college", collegeId],
    queryFn: () => api.get(`/router/college/${collegeId}`),
    enabled: !!collegeId,
  })
}

export function useUpdateCollege(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (updates) => api.patch(`/router/college/${collegeId}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["college", collegeId] })
    },
  })
}
