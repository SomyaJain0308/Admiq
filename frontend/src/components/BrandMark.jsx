import { cn } from "@/lib/utils"

// Same triangle glyph as the marketing landing page's brand mark and
// favicon (frontend/home/index.html), extracted into one component so the
// authenticated app (sidebar, login, loading/error screens) shares the
// exact same identity instead of a plain text "AdmiQ" wordmark standing
// in for a logo.
export function BrandMark({ size = 28, className }) {
  return (
    <span
      className={cn("brand-mark", className)}
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 32 32"
        width={size * 0.62}
        height={size * 0.62}
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M16 7 L24 24 H20.2 L18.3 19.5 H13.7 L11.8 24 H8 Z M16 12.2 L14.2 16.4 H17.8 Z" />
      </svg>
    </span>
  )
}
