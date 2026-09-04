import { useEffect, useState } from "react"

// Matches the key the no-flash inline script in home/index.html reads
// before first paint, and the one the static landing page (index.html)
// uses - keeping the two in sync means a theme choice made in the
// dashboard is respected on the landing page too, and vice versa.
const THEME_KEY = "admiq-theme"

function getInitialTheme() {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === "light" || stored === "dark") return stored
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

export function useTheme() {
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    localStorage.setItem(THEME_KEY, theme)
    // Keep the mobile browser chrome (address bar) in sync too - the
    // meta tag is set synchronously on first load by the no-flash script
    // in home/index.html, this just keeps it correct after a manual toggle.
    const meta = document.getElementById("theme-color-meta")
    if (meta) meta.content = theme === "dark" ? "#0a0a0a" : "#ffffff"
  }, [theme])

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"))
  }

  return { theme, toggleTheme }
}
