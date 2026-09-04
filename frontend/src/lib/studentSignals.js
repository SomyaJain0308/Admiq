import { TriangleAlert, Building2, UserCheck, AlertOctagon } from "lucide-react"

// Condenses the richer signal detail shown in full on the student page
// (StudentDetail.jsx) into a small, ordered set of chips for scanning a
// list of many students at once. Ordered roughly by how urgently a staff
// member would want to notice it - "gone quiet" outranks a garden-variety
// concern, which outranks just knowing a guardian is involved.
export function getSignalChips(signals = {}) {
  const chips = []

  if (signals.dropoff_reason) {
    chips.push({
      key: "dropoff",
      icon: AlertOctagon,
      label: "At risk",
      title: signals.dropoff_reason,
      className:
        "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300",
    })
  }

  if (signals.concerns?.length) {
    chips.push({
      key: "concerns",
      icon: TriangleAlert,
      label: `${signals.concerns.length} concern${signals.concerns.length > 1 ? "s" : ""}`,
      title: signals.concerns.join("; "),
      className:
        "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300",
    })
  }

  if (signals.competing_colleges?.length) {
    chips.push({
      key: "competing",
      icon: Building2,
      label: `${signals.competing_colleges.length} competing`,
      title: signals.competing_colleges.join(", "),
      className:
        "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950 dark:text-violet-300",
    })
  }

  if (signals.guardian_involvement) {
    chips.push({
      key: "guardian",
      icon: UserCheck,
      label: "Guardian involved",
      title: signals.guardian_involvement,
      className:
        "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
    })
  }

  return chips
}
