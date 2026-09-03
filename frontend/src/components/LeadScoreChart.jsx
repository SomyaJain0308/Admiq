import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from "recharts"

const BUCKETS = [
  { label: "0-9", min: 0, max: 9, color: "#94a3b8" },
  { label: "10-19", min: 10, max: 19, color: "#94a3b8" },
  { label: "20-29", min: 20, max: 29, color: "#94a3b8" },
  { label: "30-39", min: 30, max: 39, color: "#94a3b8" },
  { label: "40-49", min: 40, max: 49, color: "#f59e0b" },
  { label: "50-59", min: 50, max: 59, color: "#f59e0b" },
  { label: "60-69", min: 60, max: 69, color: "#f59e0b" },
  { label: "70-79", min: 70, max: 79, color: "#ef4444" },
  { label: "80-89", min: 80, max: 89, color: "#ef4444" },
  { label: "90-100", min: 90, max: 100, color: "#ef4444" },
]

export function LeadScoreChart({ students }) {
  const data = BUCKETS.map((bucket) => ({
    label: bucket.label,
    count: students.filter((s) => (s.lead_score ?? 0) >= bucket.min && (s.lead_score ?? 0) <= bucket.max).length,
    color: bucket.color,
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip
          formatter={(value) => [value, "Students"]}
          labelFormatter={(label) => `Lead score ${label}`}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
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
