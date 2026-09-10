import { useSyncExternalStore } from "react"

// Generic media-query hook, built on useSyncExternalStore rather than a
// state+effect pair - matchMedia is exactly the kind of external, mutable
// source (it changes on its own timeline, outside of React) that hook exists
// for, and it keeps `matches` correct on the very first render with no
// separate "sync on mount" effect needed.
function subscribe(query, onChange) {
  const mediaQueryList = window.matchMedia(query)
  mediaQueryList.addEventListener("change", onChange)
  return () => mediaQueryList.removeEventListener("change", onChange)
}

export function useMediaQuery(query) {
  return useSyncExternalStore(
    (onChange) => subscribe(query, onChange),
    () => window.matchMedia(query).matches
  )
}

// Matches Tailwind's default `lg` breakpoint, which is where DashboardLayout
// switches the sidebar from an off-canvas drawer to a static, always-visible
// column. Kept as a named export so the breakpoint lives in one place instead
// of being duplicated as a magic string everywhere it's needed.
export function useIsDesktopViewport() {
  return useMediaQuery("(min-width: 1024px)")
}
