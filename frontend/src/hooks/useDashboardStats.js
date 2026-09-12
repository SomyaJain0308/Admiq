import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useDashboardStats(collegeId) {
  return useQuery({
    queryKey: ["dashboard-stats", collegeId],
    queryFn: () => api.get(`/router/dashboard/${collegeId}/stats`),
    enabled: !!collegeId,
    // Same overview page as the queue/lead-score widgets, which poll at
    // 15-60s - a slower interval here is fine since nothing on this page
    // needs second-by-second accuracy the way an open support inbox does.
    refetchInterval: 60_000,
  })
}
