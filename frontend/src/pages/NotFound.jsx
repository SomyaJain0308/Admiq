import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { AuthShell } from "@/components/AuthShell"
import { BrandMark } from "@/components/BrandMark"

// Reuses AuthShell's dot-grid + glow background rather than a bare centered
// div - a 404 is a real (if rare) first thing someone sees, and previously
// it was the one screen in the app with zero brand identity: no mark, no
// background treatment, nothing tying it to the rest of the product.
export default function NotFound() {
  return (
    <AuthShell>
      <div className="flex flex-col items-center gap-3 text-center">
        <BrandMark size={36} />
        <h1 className="font-display text-4xl font-semibold tracking-tight">404</h1>
        <p className="text-muted-foreground">This page doesn't exist.</p>
        <Button asChild className="mt-2">
          <Link to="/">Back to dashboard</Link>
        </Button>
      </div>
    </AuthShell>
  )
}
