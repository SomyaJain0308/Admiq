import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { LayoutDashboard, Inbox, Users, GraduationCap, Settings, LogOut, Menu, X } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const navItems = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/queue", label: "Low-confidence queue", icon: Inbox },
  { to: "/staff", label: "Staff", icon: Users },
  { to: "/students", label: "Students", icon: GraduationCap },
  { to: "/settings", label: "College settings", icon: Settings },
]

export function DashboardLayout() {
  const { user, logout } = useAuth()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex min-h-screen">
      {/* Mobile top bar - only shown below lg, where the sidebar is hidden by default */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b bg-background px-4 lg:hidden">
        <span className="text-lg font-semibold">Admiq</span>
        <Button variant="ghost" size="icon" onClick={() => setMobileNavOpen(true)}>
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
        <div className="mb-6 flex items-center justify-between px-2">
          <span className="text-lg font-semibold">Admiq</span>
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileNavOpen(false)}>
            <X className="size-5" />
          </Button>
        </div>
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
          <Button variant="ghost" size="sm" className="mt-1 w-full justify-start gap-2" onClick={logout}>
            <LogOut className="size-4" />
            Log out
          </Button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-4 pt-20 sm:p-8 lg:pt-8">
        <Outlet />
      </main>
    </div>
  )
}
