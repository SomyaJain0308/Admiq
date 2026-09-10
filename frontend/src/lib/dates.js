// Shared by MessageStudentBox and ReplyToQueryDialog - both let staff opt an
// answer into an expiry date, with the same 30-day default and the same
// yyyy-mm-dd formatting <input type="date"> needs.

export function defaultExpiryDate() {
  const d = new Date()
  d.setDate(d.getDate() + 30)
  return d.toISOString().slice(0, 10) // yyyy-mm-dd, for <input type="date">
}

export function today() {
  return new Date().toISOString().slice(0, 10)
}
