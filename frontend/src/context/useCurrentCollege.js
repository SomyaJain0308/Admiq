import { useContext } from "react"
import { CollegeContext } from "@/context/college-context"

export function useCurrentCollege() {
  const ctx = useContext(CollegeContext)
  if (!ctx) {
    throw new Error("useCurrentCollege must be used within a CollegeProvider")
  }
  return ctx
}
