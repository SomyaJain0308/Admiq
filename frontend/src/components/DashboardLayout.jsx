import { useEffect, useRef, useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { LayoutDashboard, Inbox, Users, GraduationCap, FileText, Settings, LogOut, Menu, X, Moon, Sun, ChevronsUpDown, Check } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useTheme } from "@/hooks/useTheme"
import { Button } from "@/components/ui/button"
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
    function handleKeyDown(e) {
      if (e.key === "Escape") setCollegeMenuOpen(false)
    }
    document.addEventListener("pointerdown", handlePointerDown)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [collegeMenuOpen])

  return (
    <div className="flex min-h-screen">
      {/* Mobile top bar - only shown below lg, where the sidebar is hidden by default */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b bg-background px-4 lg:hidden">
        <span className="text-lg font-semibold">AdmiQ</span>
        <Button variant="ghost" size="icon" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation menu">
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
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r bg-muted/20 p-4 transition-transform lg:static lg:z-auto lg:w-60 lg:translate-x-0",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-4 flex items-center justify-between px-2">
          <span className="text-lg font-semibold">AdmiQ</span>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation menu">
            <X className="size-5" />
          </Button>
        </div>

        {colleges.length > 1 && (
          <div className="relative mb-4 px-2" ref={collegeMenuRef}>
            <button
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
              <div role="listbox" className="absolute top-full right-2 left-2 z-10 mt-1 rounded-md border bg-popover p-1 shadow-md">
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
                    className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
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
              {label}
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

      <main className="flex-1 overflow-y-auto p-4 pt-20 sm:p-8 lg:pt-8">
        <Outlet />
      </main>
    </div>
  )
}
