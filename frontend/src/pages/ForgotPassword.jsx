import { useState } from "react"
import { Link } from "react-router-dom"
import { ArrowLeft, MailCheck } from "lucide-react"
import { api, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
import { BrandMark } from "@/components/BrandMark"
import { AuthShell } from "@/components/AuthShell"

export default function ForgotPassword() {
  const [email, setEmail] = useState("")
  const [error, setError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await api.forgotPassword(email)
      // Show the same success state whether or not the email is actually
      // registered - the backend responds identically either way so this
      // page can't be used to check who has an account.
      setSubmitted(true)
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Please wait a while and try again.")
      } else {
        setError("Something went wrong. Please try again.")
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <Card className="overflow-hidden shadow-[var(--shadow-lg)]">
        <div className="-mt-6 h-1 bg-gradient-brand" />
        {submitted ? (
          <>
            <CardHeader>
              <BrandMark size={36} className="mb-3" />
              <MailCheck className="mb-2 size-6 text-muted-foreground" />
              <CardTitle className="font-display text-xl">Check your email</CardTitle>
              <CardDescription>
                If an account exists for {email}, we've sent a link to reset the password. It expires in 15
                minutes.
              </CardDescription>
            </CardHeader>
            <CardFooter>
              <Button asChild variant="ghost" className="w-full">
                <Link to="/login">
                  <ArrowLeft className="size-4" />
                  Back to login
                </Link>
              </Button>
            </CardFooter>
          </>
        ) : (
          <>
            <CardHeader>
              <BrandMark size={36} className="mb-3" />
              <CardTitle className="font-display text-xl">Forgot password?</CardTitle>
              <CardDescription>
                Enter your staff email and we'll send you a link to reset your password.
              </CardDescription>
            </CardHeader>
            <form onSubmit={handleSubmit}>
              <CardContent className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
                <p className="text-xs text-muted-foreground">
                  Forgot your email too? Staff accounts are set up by your college admin - reach out to them
                  directly to get your login email confirmed.
                </p>
              </CardContent>
              <CardFooter className="flex flex-col gap-2">
                <Button type="submit" className="w-full" disabled={isSubmitting}>
                  {isSubmitting ? "Sending..." : "Send reset link"}
                </Button>
                <Button asChild variant="ghost" className="w-full">
                  <Link to="/login">
                    <ArrowLeft className="size-4" />
                    Back to login
                  </Link>
                </Button>
              </CardFooter>
            </form>
          </>
        )}
      </Card>
    </AuthShell>
  )
}
