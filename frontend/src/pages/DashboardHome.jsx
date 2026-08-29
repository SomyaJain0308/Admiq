import { useAuth } from "@/context/AuthContext"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

export default function DashboardHome() {
  const { user } = useAuth()
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Welcome back{user?.staff_name ? `, ${user.staff_name}` : ""}</h1>
        <p className="text-muted-foreground">Here's what's happening across your colleges.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Getting started</CardTitle>
          <CardDescription>
            Use the sidebar to jump into the low-confidence query queue, manage staff, or view student conversations.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  )
}
