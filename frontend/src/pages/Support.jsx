import { Phone, MessageCircle } from "lucide-react"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

// Single source of truth for the founder's number - both the tel: and
// wa.me links below are derived from it, so there's only one place to
// update if it ever changes.
const FOUNDER_PHONE_DISPLAY = "+91 74178 98321"
const FOUNDER_PHONE_TEL = "+917417898321"
const FOUNDER_PHONE_WHATSAPP = "917417898321" // wa.me wants digits only, no "+"

export default function Support() {
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Support</h1>
        <p className="mt-1 text-muted-foreground">
          Stuck on anything — a bug, a question, something that just looks wrong — skip the
          ticket queue and reach the founder directly.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Talk to the founder</CardTitle>
          <CardDescription>{FOUNDER_PHONE_DISPLAY} · usually reachable during the day, IST</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row">
          <Button asChild size="lg" className="flex-1 gap-2">
            <a href={`tel:${FOUNDER_PHONE_TEL}`}>
              <Phone className="size-4" />
              Call now
            </a>
          </Button>
          <Button asChild variant="outline" size="lg" className="flex-1 gap-2">
            <a
              href={`https://wa.me/${FOUNDER_PHONE_WHATSAPP}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              <MessageCircle className="size-4" />
              WhatsApp
            </a>
          </Button>
        </CardContent>
      </Card>

      <p className="text-sm text-muted-foreground">
        No issue is too small — if something's slowing your team down, that's exactly what this
        is for.
      </p>
    </div>
  )
}
