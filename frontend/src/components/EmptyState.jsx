import { SearchX } from "lucide-react"
import { Button } from "@/components/ui/button"

// Two flavors of "nothing to show here", deliberately styled differently so
// they read as different situations rather than the same box everywhere:
//
// - EmptyState: there's structurally no data yet (an empty table, an empty
//   queue). Heavier treatment - dashed card, icon in a circle - because it's
//   often the first thing a new user sees and may want a next action.
// - FilteredEmptyState: there IS data, it's just hidden by the current
//   search/filter. Lighter treatment - no card, smaller icon - because it's
//   transient and one click (clearing the filter) away from a normal view.

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed py-16 text-center">
      {Icon && (
        <div className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Icon className="size-6 text-muted-foreground" />
        </div>
      )}
      <div className="flex flex-col gap-1">
        <p className="font-medium">{title}</p>
        {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      </div>
      {action && (
        <Button variant="outline" size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}

export function FilteredEmptyState({ query, onClear, itemLabel = "results" }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 py-10 text-center">
      <SearchX className="size-5 text-muted-foreground/60" />
      <p className="flex flex-wrap items-center justify-center gap-x-1 gap-y-1 text-sm text-muted-foreground">
        <span>
          No {itemLabel} match &quot;{query}&quot;.
        </span>
        <Button variant="link" size="sm" className="h-auto p-0 text-sm" onClick={onClear}>
          Clear search
        </Button>
      </p>
    </div>
  )
}
