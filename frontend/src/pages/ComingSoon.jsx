export default function ComingSoon({ title }) {
  return (
    <div className="animate-page-in flex flex-col gap-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-muted-foreground">This page is coming soon.</p>
    </div>
  )
}
