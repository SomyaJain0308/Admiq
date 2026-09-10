import { useEffect, useRef } from "react"
import { useLocation } from "react-router-dom"

// SPA route changes don't trigger a full page load, so none of the signals a
// screen-reader or keyboard user would normally get for "you're on a new
// page" happen on their own: focus stays wherever it was (often on the nav
// link that was just clicked), and the document title doesn't change. A
// sighted mouse user just sees the content swap and doesn't need either.
//
// `mainRef` should point at the `<main>` landmark; it needs `tabIndex={-1}`
// so it's programmatically focusable without becoming a regular Tab stop.
// `getTitle` maps the current location to a page title/heading.
export function useRouteAnnouncer(mainRef, getTitle) {
  const location = useLocation()
  const isFirstRender = useRef(true)

  useEffect(() => {
    document.title = getTitle(location)

    // Skip the very first render: the browser already handles initial focus
    // (and any deep link the person followed) on first load, so moving
    // focus to <main> at that point would just discard it for no reason.
    // Only actual in-app navigations - a sidebar click, a "view student"
    // link, browser back/forward - should redirect focus.
    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }

    mainRef.current?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname])
}
