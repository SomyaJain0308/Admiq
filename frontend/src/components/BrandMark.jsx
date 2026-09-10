import { cn } from "@/lib/utils"

// Same triangle glyph as the marketing landing page's brand mark and
// favicon (frontend/home/index.html), extracted into one component so the
// authenticated app (sidebar, login, loading/error screens) shares the
// exact same identity instead of a plain text "AdmiQ" wordmark standing
// in for a logo.
//
// The landing page draws this as a dark rounded square with a light
// triangle cut into it, via a raw inline <svg> with hardcoded fill colors
// (#18181b / #fafafa) - that doesn't adapt to the dashboard's light/dark
// theme. This uses bg-foreground/text-background instead so the square is
// always the opposite of the page background, in either theme, without
// depending on a ".brand-mark" CSS class (the landing page only ever
// defined sizing for that class, never a background or color - the square
// there comes entirely from the inline SVG's own fill attributes).
export function BrandMark({ size = 28, className }) {
  return (
    <span
      className={cn("brand-mark inline-flex shrink-0 items-center justify-center rounded-[7px] bg-foreground text-background", className)}
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
