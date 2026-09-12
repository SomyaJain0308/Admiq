import { useQuery } from "@tanstack/react-query"

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// GET /router/college is gated by X-Admin-Token (settings.internal_task_token)
// - a DIFFERENT shared secret from the X-Cost-Reporting-Token the stats
// endpoint uses (see backend/app/api/v1/routers/colleges.py's
// _verify_admin_token vs costs.py's _verify_token). Listing every college's
// name/contact info is a separate, more sensitive capability than reading
// one college's cost stats, so it deliberately isn't unlocked by the same
// token - this hook only ever sends what the person typed into the
// "admin token" field, never the cost-reporting token.
async function fetchColleges(adminToken) {
  const response = await fetch(`${API_BASE_URL}/router/college`, {
    headers: { "X-Admin-Token": adminToken },
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

// Opt-in only - callers gate this behind the person explicitly asking to
// list colleges (see InternalCostDashboard's "Load colleges" button) rather
// than firing as soon as something is typed into the admin-token field.
export function useInternalCollegeList(adminToken, { enabled }) {
  return useQuery({
    queryKey: ["internal-college-list", adminToken],
    queryFn: () => fetchColleges(adminToken),
    enabled: !!adminToken && !!enabled,
    retry: false,
  })
}
