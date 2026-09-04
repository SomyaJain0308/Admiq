import { useState } from "react"
import { useTheme } from "@/hooks/useTheme"

// Buckets share the cold/warm/hot band cutoffs in lib/leadScore.js (0-39,
// 40-69, 70-100) just split into deciles for a readable histogram shape.
const BUCKETS = [
  { label: "0-9", min: 0, max: 9, band: "cold" },
  { label: "10-19", min: 10, max: 19, band: "cold" },
  { label: "20-29", min: 20, max: 29, band: "cold" },
  { label: "30-39", min: 30, max: 39, band: "cold" },
  { label: "40-49", min: 40, max: 49, band: "warm" },
  { label: "50-59", min: 50, max: 59, band: "warm" },
  { label: "60-69", min: 60, max: 69, band: "warm" },
  { label: "70-79", min: 70, max: 79, band: "hot" },
  { label: "80-89", min: 80, max: 89, band: "hot" },
  { label: "90-100", min: 90, max: 100, band: "hot" },
]

// Same hex values as index.css's --hot/--warm/--cold, per theme - kept as
// real color values (not CSS vars) because they're written into an inline
// `style` here, same reasoning as before.
const BAND_COLORS = {
  light: { cold: "#71717a", warm: "#b45309", hot: "#b91c1c" },
  dark: { cold: "#a1a1aa", warm: "#fbbf24", hot: "#f87171" },
}

// A hand-rolled bar chart instead of recharts - this was the only chart in
// the app, and recharts costs ~350kB (gzip ~100kB) for something 10 flexbox
// columns render just as well, with a smaller, simpler, dependency-free
// component and no extra chunk to fetch.
export function LeadScoreChart({ students }) {
  const { theme } = useTheme()
  const colors = BAND_COLORS[theme]
  const [hoveredIndex, setHoveredIndex] = useState(null)

  const data = BUCKETS.map((bucket) => ({
    ...bucket,
    count: students.filter((s) => (s.lead_score ?? 0) >= bucket.min && (s.lead_score ?? 0) <= bucket.max).length,
    color: colors[bucket.band],
  }))
  const maxCount = Math.max(1, ...data.map((d) => d.count))

  return (
    <div className="flex h-[220px] items-end gap-1.5" role="img" aria-label="Bar chart of student lead scores, from cold to hot">
      {data.map((bucket, i) => (
        <button
          key={bucket.label}
          type="button"
          className="relative flex h-full flex-1 flex-col items-center justify-end gap-1.5 rounded-sm border-0 bg-transparent p-0 outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          onMouseEnter={() => setHoveredIndex(i)}
          onMouseLeave={() => setHoveredIndex(null)}
          onFocus={() => setHoveredIndex(i)}
          onBlur={() => setHoveredIndex(null)}
          aria-label={`Lead score ${bucket.label}: ${bucket.count} student${bucket.count === 1 ? "" : "s"}`}
        >
          {hoveredIndex === i && (
            <div className="pointer-events-none absolute bottom-full z-10 mb-1.5 rounded-md border bg-popover px-2 py-1 text-xs whitespace-nowrap text-popover-foreground shadow-md">
              {bucket.count} student{bucket.count === 1 ? "" : "s"}
            </div>
          )}
          <div
            className="w-full rounded-t-sm transition-[height,opacity] duration-150"
            style={{
              height: `${(bucket.count / maxCount) * 100}%`,
              minHeight: bucket.count > 0 ? "3px" : 0,
              backgroundColor: bucket.color,
              opacity: hoveredIndex === null || hoveredIndex === i ? 1 : 0.5,
            }}
          />
          <span className="text-[10px] text-muted-foreground">{bucket.label}</span>
        </button>
      ))}
    </div>
  )
}
