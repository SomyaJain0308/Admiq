import { useState } from "react"

// Shared by StaffManagement, StudentsList, and LowConfidenceQueue: whenever
// the thing that determines "which list you're looking at" changes (a
// search term, an assignment filter, the open/resolved tab...), whatever
// page you were on stops being meaningful and should reset to 1.
//
// `key` should be a value (or a string combining several) that changes
// whenever any relevant filter changes - e.g. `${search}|${assignedTo}`.
//
// Adjusts state directly during render (React's own recommended pattern for
// "reset state when a prop/derived value changes") rather than a useEffect -
// no extra render/flicker, and avoids the setState-in-effect lint warning.
export function useResetPageOnChange(key) {
  const [page, setPage] = useState(1)
  const [prevKey, setPrevKey] = useState(key)

  if (key !== prevKey) {
    setPrevKey(key)
    setPage(1)
  }

  return [page, setPage]
}
