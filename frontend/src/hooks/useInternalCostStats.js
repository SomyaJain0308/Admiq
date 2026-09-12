import { useQuery } from "@tanstack/react-query"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Deliberately NOT going through lib/api.js's `api` client - that client
// attaches the college-staff JWT (Authorization: Bearer ...) to every
// request, which is exactly the credential this endpoint refuses to accept.
// backend/app/api/v1/routers/costs.py gates /internal/costs on a separate
// shared secret (X-Cost-Reporting-Token) precisely so a staff login can
// never reach it - this hook mirrors that by sending only the token the
// person typed into InternalCostDashboard, nothing from tokenStore.js.
async function fetchCostStats(collegeId, token) {
  const response = await fetch(`${API_BASE_URL}/internal/costs/${collegeId}/stats`, {
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

// Only runs once both a college id and a token are present - callers gate
// entry behind a small form (see InternalCostDashboard.jsx) rather than
// this hook silently firing an unauthenticated request on mount.
export function useInternalCostStats(collegeId, token) {
  return useQuery({
    queryKey: ["internal-cost-stats", collegeId, token],
    queryFn: () => fetchCostStats(collegeId, token),
    enabled: !!collegeId && !!token,
    retry: false,
    refetchInterval: 60_000,
  })
}
