import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { BrandMark } from "@/components/BrandMark"

export default function NotFound() {
  return (
    <div className="animate-page-in flex min-h-screen flex-col items-center justify-center gap-3 text-center">
      <BrandMark size={40} className="mb-2 opacity-80" />
      <h1 className="font-display text-5xl font-semibold">404</h1>
      <p className="text-muted-foreground">This page doesn't exist.</p>
      <Button asChild className="mt-2">
        <Link to="/">Back to dashboard</Link>
      </Button>
    </div>
  )
}
