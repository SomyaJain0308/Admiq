import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from "recharts"
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

// Recharts needs real color values (it writes them straight into SVG fill
// attributes, which don't resolve CSS custom properties reliably), so the
// hot/warm/cold hexes from index.css are mirrored here per theme rather
// than read from the CSS var at render time.
const BAND_COLORS = {
  light: { cold: "#71717a", warm: "#b45309", hot: "#b91c1c" },
  dark: { cold: "#a1a1aa", warm: "#fbbf24", hot: "#f87171" },
}

export function LeadScoreChart({ students }) {
  const { theme } = useTheme()
  const colors = BAND_COLORS[theme]

  const data = BUCKETS.map((bucket) => ({
    label: bucket.label,
    count: students.filter((s) => (s.lead_score ?? 0) >= bucket.min && (s.lead_score ?? 0) <= bucket.max).length,
    color: colors[bucket.band],
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip
          formatter={(value) => [value, "Students"]}
          labelFormatter={(label) => `Lead score ${label}`}
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            background: "var(--popover)",
            borderColor: "var(--border)",
            color: "var(--popover-foreground)",
          }}
          labelStyle={{ color: "var(--popover-foreground)" }}
          itemStyle={{ color: "var(--popover-foreground)" }}
        />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
