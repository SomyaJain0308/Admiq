import { useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useCollegeDetail, useUpdateCollege } from "@/hooks/useCollege"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"

export default function CollegeSettings() {
  const { college: currentCollege, hasNoCollege } = useCurrentCollege()
  const { data: college, isLoading } = useCollegeDetail(currentCollege?.college_id)
  const updateMutation = useUpdateCollege(currentCollege?.college_id)

  if (hasNoCollege) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">College settings</h1>
        <p className="text-muted-foreground">Your account isn't linked to a college yet. Contact an admin to get set up.</p>
      </div>
    )
  }

  if (isLoading || !college) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Loading college settings...
      </div>
    )
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">College settings</h1>
        <p className="text-muted-foreground">Basic info and admissions assistant configuration.</p>
      </div>

      {/* key={college.college_id} makes React remount this form (and re-run
          its useState initializer) whenever the selected college changes,
          instead of needing a useEffect to sync form state to fetched data -
          this is React's own recommended pattern for "reset state when a
          prop changes" rather than calling setState from inside an effect. */}
      <CollegeSettingsForm key={college.college_id} college={college} updateMutation={updateMutation} />
    </div>
  )
}

function CollegeSettingsForm({ college, updateMutation }) {
  const [form, setForm] = useState(() => ({
    college_name: college.college_name,
    college_phone: college.college_phone,
    college_email: college.college_email,
    strengthsText: (college.college_strengths || []).join("\n"),
  }))

  async function handleSubmit(e) {
    e.preventDefault()
    const college_strengths = form.strengthsText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)

    try {
      await updateMutation.mutateAsync({
        college_name: form.college_name,
        college_phone: form.college_phone,
        college_email: form.college_email,
        college_strengths,
      })
      toast.success("College settings saved.")
    } catch (err) {
      toast.error(err?.message || "Failed to save changes. Please try again.")
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Contact info</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="college_name">College name</Label>
            <Input
              id="college_name"
              required
              minLength={2}
              value={form.college_name}
              onChange={(e) => setForm((f) => ({ ...f, college_name: e.target.value }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="college_phone">Phone</Label>
              <Input
                id="college_phone"
                required
                minLength={10}
                value={form.college_phone}
                onChange={(e) => setForm((f) => ({ ...f, college_phone: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="college_email">Email</Label>
              <Input
                id="college_email"
                type="email"
                required
                value={form.college_email}
                onChange={(e) => setForm((f) => ({ ...f, college_email: e.target.value }))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Key strengths</CardTitle>
          <CardDescription>
            One per line. The assistant uses these to write personalized check-in messages to students who've gone
            quiet - things like low fees, strong placement rates, or hostel facilities.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Textarea
            rows={6}
            value={form.strengthsText}
            onChange={(e) => setForm((f) => ({ ...f, strengthsText: e.target.value }))}
            placeholder={"Low tuition fees vs regional private colleges\n95% placement rate over the last 3 years\nOn-campus hostel with 24/7 security"}
          />
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={updateMutation.isPending}>
            {updateMutation.isPending ? "Saving..." : "Save changes"}
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
