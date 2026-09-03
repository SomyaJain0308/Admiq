import { useMemo, useState } from "react"

// Client-side pagination - the backend doesn't support skip/limit yet, so this
// doesn't reduce the actual network payload, but it does fix the real
// day-to-day problem (an endless unscrollable table). A proper server-side
// paginated endpoint is the eventual right fix once data volume actually
// makes fetching everything slow, not just visually unwieldy.
export function usePagination(items, pageSize = 15) {
  const [requestedPage, setPage] = useState(1)
  const totalPages = Math.max(1, Math.ceil((items?.length || 0) / pageSize))

  // Clamp during render rather than in an effect: if the underlying list
  // shrinks (e.g. a search filter) and the requested page no longer exists,
  // this just derives the valid page directly instead of rendering a stale
  // out-of-range page and correcting it a tick later.
  const page = Math.min(requestedPage, totalPages)

  const pageItems = useMemo(() => {
    const start = (page - 1) * pageSize
    return (items || []).slice(start, start + pageSize)
  }, [items, page, pageSize])

  return { page, setPage, totalPages, pageItems }
}
