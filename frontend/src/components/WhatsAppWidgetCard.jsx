import { useState } from "react"
import { Link } from "react-router-dom"
import { Loader2, Copy, Check, MessageCircle } from "lucide-react"
import { toast } from "sonner"
import { useWhatsAppNumber } from "@/hooks/useWhatsAppNumber"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"

// Fixed brand copy for the bubble - deliberately generic (no college name)
// so the same widget reads consistently across every college's site, and
// the default first message a student sends once they tap through. Both
// live here as the single source of truth for what buildEmbedSnippet()
// generates below.
const BUBBLE_LINE_1 = "Have a question?"
const BUBBLE_LINE_2 = "Chat with Admiq"
const DEFAULT_PREFILLED_MESSAGE = "Hi, I have a question about admissions."

function buildEmbedSnippet(displayNumber) {
  const digitsOnly = displayNumber.replace(/[^0-9]/g, "")
  return `<!-- Admiq WhatsApp widget - paste just before </body> -->
<div id="admiq-wa-widget" style="position:fixed;right:20px;bottom:20px;z-index:999999;display:flex;align-items:center;gap:12px;cursor:pointer;">
  <div style="position:relative;background:#fff;border-radius:14px;padding:12px 18px;box-shadow:0 6px 20px rgba(0,0,0,.15);white-space:nowrap;">
    <div style="font-size:15px;color:#1a1a1a;font-weight:500;">${BUBBLE_LINE_1}</div>
    <div style="font-size:15px;color:#25d366;font-weight:700;">${BUBBLE_LINE_2}</div>
  </div>
  <div style="width:58px;height:58px;min-width:58px;border-radius:50%;background:#25d366;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 16px rgba(0,0,0,.25);">
    <svg viewBox="0 0 32 32" width="30" height="30" xmlns="http://www.w3.org/2000/svg">
      <path d="M16.001 3C9.11 3 3.5 8.611 3.5 15.502c0 2.42.679 4.75 1.966 6.767L3 29l6.9-2.402a12.94 12.94 0 0 0 6.101 1.554h.005c6.891 0 12.5-5.611 12.5-12.503C28.506 8.611 22.897 3 16.001 3Z" fill="#fff"/>
      <path d="M16.002 4.6c-6.01 0-10.9 4.89-10.9 10.9 0 2.14.62 4.14 1.69 5.83l.26.41-1.12 4.09 4.19-1.1.4.24a10.85 10.85 0 0 0 5.48 1.48h.004c6.01 0 10.9-4.89 10.9-10.9 0-2.91-1.13-5.65-3.19-7.71a10.83 10.83 0 0 0-7.71-3.24Z" fill="#25D366"/>
      <path d="M12.24 9.86c-.24-.54-.5-.55-.73-.56-.19-.01-.4-.01-.62-.01-.21 0-.56.08-.86.4-.29.32-1.13 1.1-1.13 2.69 0 1.58 1.16 3.11 1.32 3.33.16.21 2.24 3.59 5.53 4.89 2.74 1.08 3.29.87 3.89.81.6-.06 1.93-.79 2.2-1.55.27-.76.27-1.42.19-1.55-.08-.13-.29-.21-.6-.37-.32-.16-1.93-.95-2.23-1.06-.3-.11-.51-.16-.73.16-.21.32-.84 1.06-1.03 1.27-.19.22-.38.24-.7.08-.32-.16-1.35-.5-2.57-1.59-.95-.85-1.59-1.9-1.78-2.22-.19-.32-.02-.49.14-.65.14-.15.32-.38.48-.57.16-.19.21-.32.32-.54.11-.22.05-.4-.03-.57-.08-.16-.71-1.77-.99-2.4Z" fill="#fff"/>
    </svg>
  </div>
</div>
<script>
  (function () {
    var url = "https://wa.me/${digitsOnly}?text=" + encodeURIComponent(${JSON.stringify(DEFAULT_PREFILLED_MESSAGE)});
    document.getElementById("admiq-wa-widget").addEventListener("click", function () {
      window.open(url, "_blank", "noopener,noreferrer");
    });
  })();
</script>`
}

// Small, non-clickable stand-in for the real floating widget, scaled to
// sit inside the card instead of the corner of the viewport - staff get to
// see exactly what students will see without leaving the settings page.
function WidgetPreview() {
  return (
    <div className="relative flex h-40 items-end justify-end overflow-hidden rounded-lg border bg-muted/40 p-4">
      <div className="flex items-center gap-2">
        <div className="relative whitespace-nowrap rounded-xl bg-background px-3 py-2 shadow-md">
          <div className="text-xs font-medium">{BUBBLE_LINE_1}</div>
          <div className="text-xs font-bold text-[#25d366]">{BUBBLE_LINE_2}</div>
        </div>
        <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#25d366] shadow-md">
          <MessageCircle className="size-5 fill-white text-white" />
        </div>
      </div>
    </div>
  )
}

export function WhatsAppWidgetCard({ collegeId }) {
  const { data: whatsappNumber, isLoading } = useWhatsAppNumber(collegeId)
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(buildEmbedSnippet(whatsappNumber.display_number))
      setCopied(true)
      toast.success("Widget code copied.")
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error("Couldn't copy to clipboard - try selecting the code manually.")
    }
  }

  return (
    <Card className="shadow-elevated mt-4">
      <CardHeader>
        <CardTitle className="font-display text-base">Website widget</CardTitle>
        <CardDescription>
          A floating WhatsApp button for your college's own website. Students tap it to open a chat with
          your connected number - no separate app or login needed on their end.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Checking your WhatsApp connection...
          </div>
        ) : !whatsappNumber ? (
          <div className="flex flex-col items-start gap-3 rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            <p>
              No WhatsApp number is connected for your college yet, so there's nothing for the widget to
              link to. Reach out from the{" "}
              <Link to="/support" className="font-medium text-primary underline">
                Support
              </Link>{" "}
              page to get one set up.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <WidgetPreview />
            <p className="text-sm text-muted-foreground">
              Connected number: <span className="font-medium text-foreground">{whatsappNumber.display_number}</span>
            </p>
            <div className="flex flex-col gap-2">
              <Button type="button" variant="outline" className="w-fit gap-2" onClick={handleCopy}>
                {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                {copied ? "Copied" : "Copy website code"}
              </Button>
              <p className="text-xs text-muted-foreground">
                Paste this into your website's HTML, just before the closing <code>&lt;/body&gt;</code> tag.
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
