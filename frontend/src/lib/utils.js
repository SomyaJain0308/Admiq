import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

// Shared base styling for plain native <select> elements (AssignStaffSelect,
// the assignment filter in StudentsList) - these intentionally use a real
// <select> rather than the Radix one, so they need their own focus/border
// treatment to match the rest of the form inputs. Pass extra classes (e.g.
// "w-full", "disabled:...") through cn() at the call site rather than here,
// so each usage can still adapt to its own layout.
export const nativeSelectClassName =
  "border-input flex h-9 rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
