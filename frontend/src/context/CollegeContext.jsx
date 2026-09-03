import { createContext, useContext, useEffect, useState } from "react"
import { useAuth } from "@/context/AuthContext"

const CollegeContext = createContext(null)
const SELECTED_COLLEGE_KEY = "admiq_selected_college_id"

export function CollegeProvider({ children }) {
  const { user } = useAuth()
  const colleges = user?.colleges || []
  const [selectedCollegeId, setSelectedCollegeId] = useState(null)

  useEffect(() => {
    if (colleges.length === 0) {
      setSelectedCollegeId(null)
      return
    }
    const stored = Number(localStorage.getItem(SELECTED_COLLEGE_KEY))
    const storedIsValid = colleges.some((c) => c.college_id === stored)
    setSelectedCollegeId(storedIsValid ? stored : colleges[0].college_id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.staff_id, colleges.length])

  function selectCollege(collegeId) {
    setSelectedCollegeId(collegeId)
    localStorage.setItem(SELECTED_COLLEGE_KEY, String(collegeId))
  }

  // Falls back to the first college whenever selectedCollegeId hasn't been
  // resolved yet (e.g. the very first render right after login, before the
  // effect below has had a chance to run and set it from localStorage).
  // Without this fallback there's a real render where colleges.length > 0
  // (so hasNoCollege is false and pages proceed) but college is still null,
  // which crashes any page that reads college.college_name directly.
  const college = colleges.find((c) => c.college_id === selectedCollegeId) || colleges[0] || null

  const value = {
    college,
    colleges,
    selectCollege,
    hasNoCollege: colleges.length === 0,
  }

  return <CollegeContext.Provider value={value}>{children}</CollegeContext.Provider>
}

export function useCurrentCollege() {
  const ctx = useContext(CollegeContext)
  if (!ctx) {
    throw new Error("useCurrentCollege must be used within a CollegeProvider")
  }
  return ctx
}
