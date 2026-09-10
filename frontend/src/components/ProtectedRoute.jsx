import { Navigate, Outlet } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { BrandMark } from "@/components/BrandMark"

export function ProtectedRoute() {
  const { isAuthenticated, isBootstrapping } = useAuth()

  // Wait for the silent session-restore attempt to finish before deciding
  // whether to redirect - otherwise an already-logged-in staff member gets
  // bounced to /login for a split second on every page reload.
  if (isBootstrapping) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
        <BrandMark size={32} />
        <span className="flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" />
          Loading...
        </span>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
