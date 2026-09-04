// Matches the backend's own scoring bands conceptually (services/lead_scoring.py) -
// not an exact mirror, just a sensible display grouping for staff scanning a list.
// Colors come from the --hot/--warm/--cold tokens in index.css (the same
// "lead temperature" scale the marketing landing page uses), so light/dark
// and any future palette tweak only need to happen in one place.
export function leadScoreBand(score) {
  if (score >= 70) {
    return { label: "Hot", className: "border-hot/30 bg-hot/10 text-hot-foreground dark:text-hot" }
  }
  if (score >= 40) {
    return { label: "Warm", className: "border-warm/30 bg-warm/10 text-warm-foreground dark:text-warm" }
  }
  return { label: "Cold", className: "border-cold/30 bg-cold/10 text-cold-foreground dark:text-cold" }
}
