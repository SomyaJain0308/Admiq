import { useQuery } from "@tanstack/react-query"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Same reasoning as useInternalCostStats.js - direct fetch with the
// cost-reporting token, deliberately bypassing lib/api.js's JWT injection.
async function fetchStudentCostEvents(collegeId, studentId, token) {
  const response = await fetch(`${API_BASE_URL}/internal/costs/${collegeId}/students/${studentId}/events`, {
    headers: { "X-Cost-Reporting-Token": token },
  })
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const data = await response.json()
      detail = data?.detail || detail
    } catch {
      // no JSON body - keep the generic message
    }
    const error = new Error(detail)
    error.status = response.status
    throw error
  }
  return response.json()
}

// Only enabled while a drill-down dialog for a specific student is open -
// see InternalCostDashboard's StudentEventsDialog - so opening/closing the
// top-students table doesn't fire a request per row.
export function useInternalStudentCostEvents(collegeId, studentId, token, { enabled }) {
  return useQuery({
    queryKey: ["internal-student-cost-events", collegeId, studentId, token],
    queryFn: () => fetchStudentCostEvents(collegeId, studentId, token),
    enabled: !!collegeId && !!studentId && !!token && !!enabled,
    retry: false,
  })
}
