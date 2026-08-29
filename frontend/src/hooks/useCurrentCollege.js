import { useAuth } from "@/context/AuthContext"

// Single-college assumption for now: staff who belong to more than one
// college will always see their first one. A real college switcher (reading
// from the same user.colleges list) is a natural next addition once that's
// actually needed - nothing here would need to change to support it later,
// this hook is already the single place that decision is made.
export function useCurrentCollege() {
  const { user } = useAuth()
  const colleges = user?.colleges || []
  return {
    college: colleges[0] || null,
    colleges,
    hasNoCollege: colleges.length === 0,
  }
}
