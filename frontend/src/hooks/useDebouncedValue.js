import { useEffect, useState } from "react"

// Delays reflecting a fast-changing value (like search input) until it's
// stopped changing for `delayMs` - used so search doesn't fire a network
// request on every keystroke now that search is server-side.
export function useDebouncedValue(value, delayMs = 350) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timeout)
  }, [value, delayMs])

  return debounced
}
