import { useEffect, useRef, useState } from "react"
import { NavLink, Outlet, matchPath } from "react-router-dom"
import { LayoutDashboard, Inbox, Users, GraduationCap, FileText, Settings, LifeBuoy, LogOut, Menu, X, Moon, Sun, ChevronsUpDown, Check } from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { useCurrentCollege } from "@/context/useCurrentCollege"
import { useTheme } from "@/hooks/useTheme"
import { useLowConfidenceQueries } from "@/hooks/useLowConfidenceQueue"
import { useIsDesktopViewport } from "@/hooks/useMediaQuery"
import { useRouteAnnouncer } from "@/hooks/useRouteAnnouncer"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { BrandMark } from "@/components/BrandMark"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/queue", label: "Low-confidence queue", icon: Inbox },
  { to: "/staff", label: "Staff", icon: Users },
  { to: "/students", label: "Students", icon: GraduationCap },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/settings", label: "College settings", icon: Settings },
  { to: "/support", label: "Support", icon: LifeBuoy },
]

// Keeps `document.title` meaningful on every client-side navigation (see
// useRouteAnnouncer) without needing every page component to set it
// individually. Falls back to matching against `navItems` for the routes
// that already have a nav label; /students/:studentId is handled separately
// since it isn't in that list and doesn't have a static label.
function getRouteTitle(location) {
  if (matchPath("/students/:studentId", location.pathname)) {
    return "Student details — AdmiQ"
  }
  const match = navItems.find(({ to, end }) =>
    matchPath({ path: to, end: end ?? false }, location.pathname)
  )
  return match ? `${match.label} — AdmiQ` : "AdmiQ"
}

export function DashboardLayout() {
  const { user, logout } = useAuth()
  const { college, colleges, selectCollege } = useCurrentCollege()
  const { theme, toggleTheme } = useTheme()
  const isDesktopViewport = useIsDesktopViewport()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [collegeMenuOpen, setCollegeMenuOpen] = useState(false)
  const collegeMenuRef = useRef(null)
  const collegeButtonRef = useRef(null)
  const hamburgerButtonRef = useRef(null)
  const collegeOptionRefs = useRef([])
  const mainRef = useRef(null)

  useRouteAnnouncer(mainRef, getRouteTitle)

  // Small, cheap poll (page_size=1, we only read `total`) just to drive the
  // sidebar badge - lets staff see something's waiting without having the
  // queue page itself open. The queue page's own query polls independently
  // at the same interval, so the two stay roughly in sync.
  const { data: queueData } = useLowConfidenceQueries(college?.college_id, false, { page: 1, pageSize: 1 })
  const openQueueCount = queueData?.total ?? 0

  // The college switcher is a plain div, not a native <select> or a Radix
  // popover, so nothing closes it automatically - without this it stays
  // open until the trigger button is clicked a second time, even after
  // clicking elsewhere on the page or picking a different nav item.
  useEffect(() => {
    if (!collegeMenuOpen) return
    function handlePointerDown(e) {
      if (collegeMenuRef.current && !collegeMenuRef.current.contains(e.target)) {
        setCollegeMenuOpen(false)
      }
    }
    document.addEventListener("pointerdown", handlePointerDown)
    return () => document.removeEventListener("pointerdown", handlePointerDown)
  }, [collegeMenuOpen])

  // Escape closes whichever of the two custom (non-Radix) panels is open,
  // and returns focus to the button that opened it - without this a
  // keyboard user who dismisses either one loses their place entirely.
  useEffect(() => {
    if (!collegeMenuOpen && !mobileNavOpen) return
    function handleKeyDown(e) {
      if (e.key !== "Escape") return
      if (collegeMenuOpen) {
        setCollegeMenuOpen(false)
        collegeButtonRef.current?.focus()
      } else if (mobileNavOpen) {
        setMobileNavOpen(false)
        hamburgerButtonRef.current?.focus()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [collegeMenuOpen, mobileNavOpen])

  // Moves focus into the listbox as soon as it opens (onto the currently
  // selected college, or the first one) - the ARIA listbox pattern this
  // menu intentionally uses expects the listbox itself to hold focus while
  // open, with arrow keys moving between options, rather than leaving focus
  // sitting on the trigger button.
  useEffect(() => {
    if (!collegeMenuOpen) return
    const selectedIndex = colleges.findIndex((c) => c.college_id === college?.college_id)
    collegeOptionRefs.current[selectedIndex >= 0 ? selectedIndex : 0]?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collegeMenuOpen])

  function focusCollegeOption(index) {
    const count = collegeOptionRefs.current.length
    if (count === 0) return
    collegeOptionRefs.current[(index + count) % count]?.focus()
  }

  function handleCollegeListboxKeyDown(e) {
    const currentIndex = collegeOptionRefs.current.indexOf(document.activeElement)
    if (e.key === "ArrowDown") {
      e.preventDefault()
      focusCollegeOption(currentIndex + 1)
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      focusCollegeOption(currentIndex - 1)
    } else if (e.key === "Home") {
      e.preventDefault()
      focusCollegeOption(0)
    } else if (e.key === "End") {
      e.preventDefault()
      focusCollegeOption(collegeOptionRefs.current.length - 1)
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Off-screen until focused (first Tab stop on every dashboard page) -
          without it, a keyboard user has to tab through the full nav list
          every time before reaching the actual page content. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Skip to content
      </a>

      {/* Mobile top bar - only shown below lg, where the sidebar is hidden by default */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b bg-background px-4 lg:hidden">
        <span className="flex items-center gap-2 text-lg font-semibold">
          <BrandMark size={24} />
          AdmiQ
        </span>
        <Button
          ref={hamburgerButtonRef}
          variant="ghost"
          size="icon"
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation menu"
        >
          <Menu className="size-5" />
        </Button>
      </div>

      {/* Backdrop, mobile only, closes the nav when tapped outside it. A real
          button (not a div+onClick) so it's keyboard-reachable and doesn't
          need a role worked around - the visual reset classes cancel out
          the browser's default button chrome. */}
      {mobileNavOpen && (
        <button
          type="button"
          aria-label="Close navigation menu"
          className="fixed inset-0 z-40 cursor-default appearance-none border-0 bg-black/50 p-0 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside
        // Below `lg` the drawer stays mounted and is just translated
        // off-screen when closed, so `inert` is what actually keeps it out
        // of the tab order and hidden from screen readers while closed -
        // without it, its links are still focusable and still announced
        // even though they're invisible. It's driven off the same viewport
        // check as the CSS breakpoint (rather than applied unconditionally)
        // because on desktop the sidebar is always visible and must stay
        // interactive regardless of `mobileNavOpen`.
        inert={!isDesktopViewport && !mobileNavOpen ? true : undefined}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r bg-muted/20 p-4 transition-transform lg:static lg:z-auto lg:w-60 lg:translate-x-0",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-4 flex items-center justify-between px-2">
          <span className="flex items-center gap-2 text-lg font-semibold">
            <BrandMark size={24} />
            AdmiQ
          </span>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation menu">
            <X className="size-5" />
          </Button>
        </div>

        {colleges.length > 1 && (
          <div className="relative mb-4 px-2" ref={collegeMenuRef}>
            <button
              ref={collegeButtonRef}
              type="button"
              onClick={() => setCollegeMenuOpen((o) => !o)}
              aria-haspopup="listbox"
              aria-expanded={collegeMenuOpen}
              className="flex w-full items-center justify-between rounded-md border bg-background px-2 py-1.5 text-left text-sm font-medium focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <span className="truncate">{college?.college_name}</span>
              <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
            </button>
            {collegeMenuOpen && (
              // Custom combobox: options render a checkmark icon that
              // <option> can't support, so this intentionally uses the ARIA
              // listbox pattern instead of a native <select>.
              // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
              <div
                role="listbox"
                onKeyDown={handleCollegeListboxKeyDown}
                className="absolute top-full right-2 left-2 z-10 mt-1 rounded-md border bg-popover p-1 shadow-md"
              >
                {colleges.map((c, i) => (
                  <button
                    key={c.college_id}
                    ref={(el) => {
                      collegeOptionRefs.current[i] = el
                    }}
                    type="button"
                    // See listbox comment above; this is a real <button>, so
                    // it's already keyboard-operable without extra handlers.
                    // Arrow/Home/End navigation between options is handled
                    // by the listbox's onKeyDown above, per the ARIA
                    // listbox pattern.
                    // oxlint-disable-next-line jsx-a11y/prefer-tag-over-role
                    role="option"
                    aria-selected={c.college_id === college?.college_id}
                    onClick={() => {
                      selectCollege(c.college_id)
                      setCollegeMenuOpen(false)
                      collegeButtonRef.current?.focus()
                    }}
                    className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                  >
                    <span className="truncate">{c.college_name}</span>
                    {c.college_id === college?.college_id && <Check className="size-3.5" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <nav className="flex flex-1 flex-col gap-1">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setMobileNavOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )
              }
            >
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
              {to === "/queue" && openQueueCount > 0 && (
                <Badge
                  variant="destructive"
                  className="h-5 min-w-5 justify-center rounded-full px-1 text-[11px] leading-none"
                >
                  {openQueueCount > 99 ? "99+" : openQueueCount}
                </Badge>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t pt-4">
          <p className="truncate px-2 text-xs text-muted-foreground">{user?.staff_email}</p>
          <div className="mt-1 flex items-center gap-1">
            <Button variant="ghost" size="sm" className="flex-1 justify-start gap-2" onClick={logout}>
              <LogOut className="size-4" />
              Log out
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              title="Toggle theme"
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
          </div>
        </div>
      </aside>

      {/* tabIndex={-1} makes this focusable via mainRef.current.focus() in
          useRouteAnnouncer without adding it as a regular Tab stop. Keeps a
          visible focus-visible ring (same treatment as other focusable
          elements in this layout) so a keyboard user can actually see where
          focus landed after a navigation, not just have it happen silently. */}
      <main
        id="main-content"
        ref={mainRef}
        tabIndex={-1}
        className="flex-1 overflow-y-auto p-4 pt-20 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none sm:p-8 lg:pt-8"
      >
        <Outlet />
      </main>
    </div>
  )
}
