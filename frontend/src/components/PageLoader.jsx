import { Loader2 } from "lucide-react"

// Fallback shown by the top-level <Suspense> in App.jsx while a route-split
// page chunk (StudentDetail, DocumentsPage, etc.) is downloading. Kept
// intentionally tiny/dependency-free since it has to render before any lazy
// chunk - including this one's siblings - has loaded.
export function PageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground" />
    </div>
  )
}
