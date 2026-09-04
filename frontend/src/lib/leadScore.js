// Matches the backend's own scoring bands conceptually (services/lead_scoring.py) -
// not an exact mirror, just a sensible display grouping for staff scanning a list.
// dark: variants matter here - these were light-mode-only before, which meant the
// badge rendered as a pale, out-of-place box against the dark theme's near-black
// background instead of adapting like the rest of the UI does.
export function leadScoreBand(score) {
  if (score >= 70) return { label: "Hot", className: "bg-red-100 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-300 dark:border-red-800" }
  if (score >= 40) return { label: "Warm", className: "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800" }
  return { label: "Cold", className: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700" }
}
