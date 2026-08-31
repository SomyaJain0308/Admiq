// Matches the backend's own scoring bands conceptually (services/lead_scoring.py) -
// not an exact mirror, just a sensible display grouping for staff scanning a list.
export function leadScoreBand(score) {
  if (score >= 70) return { label: "Hot", className: "bg-red-100 text-red-700 border-red-200" }
  if (score >= 40) return { label: "Warm", className: "bg-amber-100 text-amber-700 border-amber-200" }
  return { label: "Cold", className: "bg-slate-100 text-slate-600 border-slate-200" }
}
