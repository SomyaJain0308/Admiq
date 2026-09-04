import { Navigate, Outlet } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { useAuth } from "@/context/AuthContext"

export function ProtectedRoute() {
  const { isAuthenticated, isBootstrapping } = useAuth()

  // Wait for the silent session-restore attempt to finish before deciding
  // whether to redirect - otherwise an already-logged-in staff member gets
  // bounced to /login for a split second on every page reload.
  if (isBootstrapping) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading...
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
