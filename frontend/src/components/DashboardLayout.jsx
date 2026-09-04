import { useEffect, useRef, useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { LayoutDashboard, Inbox, Users, GraduationCap, FileText, Settings, LogOut, Menu, X, Moon, Sun, ChevronsUpDown, Check } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useTheme } from "@/hooks/useTheme"
import { Button } from "@/components/ui/button"
import { BrandMark } from "@/components/BrandMark"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/queue", label: "Low-confidence queue", icon: Inbox },
  { to: "/staff", label: "Staff", icon: Users },
  { to: "/students", label: "Students", icon: GraduationCap },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/settings", label: "College settings", icon: Settings },
]

export function DashboardLayout() {
  const { user, logout } = useAuth()
  const { college, colleges, selectCollege } = useCurrentCollege()
  const { theme, toggleTheme } = useTheme()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [collegeMenuOpen, setCollegeMenuOpen] = useState(false)
  const collegeMenuRef = useRef(null)
  const collegeButtonRef = useRef(null)
  const hamburgerButtonRef = useRef(null)

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

  return (
    <div className="relative flex min-h-screen">
      {/* Ambient brand-color wash behind the whole app - subtle, fixed to
          viewport so it doesn't scroll away, giving every page a bit of
          color instead of a flat gray canvas. Kept faint enough to never
          compete with content or hurt table/text contrast. */}
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div
          className="absolute top-[-280px] right-[-200px] size-[680px] rounded-full opacity-70"
          style={{ background: "radial-gradient(circle, color-mix(in oklab, var(--primary) 12%, transparent) 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-[-320px] left-[-220px] size-[680px] rounded-full opacity-60"
          style={{ background: "radial-gradient(circle, color-mix(in oklab, var(--brand-2) 10%, transparent) 0%, transparent 70%)" }}
        />
      </div>

      {/* Mobile top bar - only shown below lg, where the sidebar is hidden by default */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur-sm lg:hidden">
        <span className="flex items-center gap-2">
          <BrandMark size={24} />
          <span className="font-display text-lg font-semibold">AdmiQ</span>
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

      {/* Backdrop, mobile only, closes the nav when tapped outside it */}
      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside
        className={cn(
          "relative z-50 fixed inset-y-0 left-0 flex w-64 flex-col border-r bg-gradient-to-b from-muted/40 via-muted/15 to-transparent p-4 transition-transform duration-200 ease-[var(--ease-out)] lg:static lg:z-10 lg:w-60 lg:translate-x-0",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-5 flex items-center justify-between px-1">
          <span className="flex items-center gap-2">
            <BrandMark size={26} />
            <span className="font-display text-[15px] font-semibold">AdmiQ</span>
          </span>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation menu">
            <X className="size-5" />
          </Button>
        </div>

        {colleges.length > 1 && (
          <div className="relative mb-4 px-1" ref={collegeMenuRef}>
            <button
              ref={collegeButtonRef}
              type="button"
              onClick={() => setCollegeMenuOpen((o) => !o)}
              aria-haspopup="listbox"
              aria-expanded={collegeMenuOpen}
              className="flex w-full items-center justify-between rounded-md border bg-background px-2.5 py-1.5 text-left text-sm font-medium shadow-[var(--shadow-xs)] transition-colors hover:border-ring/40 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <span className="truncate">{college?.college_name}</span>
              <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
            </button>
            {collegeMenuOpen && (
              <div role="listbox" className="absolute top-full right-1 left-1 z-10 mt-1.5 animate-page-in rounded-md border bg-popover p-1 shadow-[var(--shadow-lg)]">
                {colleges.map((c) => (
                  <button
                    key={c.college_id}
                    type="button"
                    role="option"
                    aria-selected={c.college_id === college?.college_id}
                    onClick={() => {
                      selectCollege(c.college_id)
                      setCollegeMenuOpen(false)
                    }}
                    className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent"
                  >
                    <span className="truncate">{c.college_name}</span>
                    {c.college_id === college?.college_id && <Check className="size-3.5 text-primary" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <nav className="flex flex-1 flex-col gap-0.5">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setMobileNavOpen(false)}
              className={({ isActive }) =>
                cn(
                  "group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors duration-150",
                  isActive
                    ? "bg-gradient-brand-soft text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute top-1/2 left-0 h-4.5 w-[3px] -translate-y-1/2 rounded-full bg-gradient-brand" />
                  )}
                  <Icon className="size-4 shrink-0" />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t pt-3">
          <div className="flex items-center gap-2 px-1 py-1.5">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-brand text-xs font-semibold text-white shadow-[var(--shadow-xs)]">
              {(user?.staff_name || user?.staff_email || "?").charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0">
              {user?.staff_name && <p className="truncate text-xs font-medium">{user.staff_name}</p>}
              <p className="truncate text-xs text-muted-foreground">{user?.staff_email}</p>
            </div>
          </div>
          <div className="mt-1 flex items-center gap-1">
            <Button variant="ghost" size="sm" className="flex-1 justify-start gap-2 text-muted-foreground hover:text-foreground" onClick={logout}>
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

      <main className="relative z-10 flex-1 overflow-y-auto p-4 pt-20 sm:p-8 lg:pt-8">
        <div className="mx-auto w-full max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
