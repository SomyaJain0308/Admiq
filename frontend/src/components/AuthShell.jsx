// Shared chrome for the three unauthenticated auth screens (Login,
// ForgotPassword, ResetPassword): the dot-grid + radial glow background
// from the marketing landing page's hero (frontend/home/index.html) and a
// centered card slot. Pulled into one place instead of copy-pasted three
// times so the treatment can't drift between screens.
export function AuthShell({ children }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-muted/30 p-4">
      <div
        className="pointer-events-none absolute inset-x-[-10%] top-[-20%] h-[640px]"
        style={{
          backgroundImage:
            "radial-gradient(color-mix(in oklab, var(--foreground) 12%, transparent) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
          maskImage: "radial-gradient(ellipse 55% 50% at 50% 20%, black 0%, transparent 72%)",
          WebkitMaskImage: "radial-gradient(ellipse 55% 50% at 50% 20%, black 0%, transparent 72%)",
        }}
      />
      <div
        className="pointer-events-none absolute top-[-180px] right-[-140px] size-[600px] rounded-full opacity-90"
        style={{ background: "radial-gradient(circle, color-mix(in oklab, var(--primary) 22%, transparent) 0%, transparent 68%)" }}
      />
      <div
        className="pointer-events-none absolute bottom-[-200px] left-[-160px] size-[560px] rounded-full opacity-80"
        style={{ background: "radial-gradient(circle, color-mix(in oklab, var(--brand-2) 18%, transparent) 0%, transparent 68%)" }}
      />
      <div className="relative w-full max-w-sm">{children}</div>
    </div>
  )
}
