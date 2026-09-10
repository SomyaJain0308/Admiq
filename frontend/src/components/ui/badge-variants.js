import { cva } from "class-variance-authority"

export const badgeVariants = cva(
  "inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-medium w-fit whitespace-nowrap shrink-0 gap-1",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-white",
        outline: "text-foreground",
        // Lead-temperature variants, matching the --hot/--warm/--cold tokens
        // used elsewhere (lib/leadScore.js, LeadScoreChart.jsx) - added here
        // so any future badge use can reach for variant="hot" instead of
        // re-deriving the same border/bg/text combination inline again.
        hot: "border-hot/30 bg-hot/10 text-hot-foreground dark:text-hot",
        warm: "border-warm/30 bg-warm/10 text-warm-foreground dark:text-warm",
        cold: "border-cold/30 bg-cold/10 text-cold-foreground dark:text-cold",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)
