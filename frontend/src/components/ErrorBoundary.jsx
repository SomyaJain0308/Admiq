import { Component } from "react"
import { Button } from "@/components/ui/button"

// Error boundaries have to be class components - there's still no hook
// equivalent in React for catching render errors in children. This wraps
// the whole app so a bug in one page shows a real "something broke" screen
// instead of a blank white page.
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error("Uncaught error in app:", error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-4 text-center">
          <h1 className="text-xl font-semibold">Something went wrong</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            This page hit an unexpected error. Try reloading - if it keeps happening, let your dev know.
          </p>
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </div>
      )
    }
    return this.props.children
  }
}
