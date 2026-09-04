import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useCreateStaff, useUpdateStaff } from "@/hooks/useStaff"

const emptyForm = { staff_name: "", staff_email: "", password: "", is_active: true }

export function StaffFormDialog({ collegeId, open, onOpenChange, editingStaff }) {
  const isEditMode = !!editingStaff
  const [form, setForm] = useState(emptyForm)
  // Default to inviting new staff by email rather than setting a password
  // for them directly - only relevant in create mode.
  const [sendInvite, setSendInvite] = useState(true)

  const createMutation = useCreateStaff(collegeId)
  const updateMutation = useUpdateStaff(collegeId)
  const mutation = isEditMode ? updateMutation : createMutation

  useEffect(() => {
    if (open) {
      setForm(
        isEditMode
          ? { staff_name: editingStaff.staff_name, staff_email: editingStaff.staff_email, password: "", is_active: editingStaff.is_active }
          : emptyForm
      )
      setSendInvite(true)
      mutation.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editingStaff])

  async function handleSubmit(e) {
    e.preventDefault()
    try {
      if (isEditMode) {
        // Only send fields that actually changed / were filled in - an empty
        // password field means "leave it unchanged", not "set it to empty".
        const updates = { staff_name: form.staff_name, staff_email: form.staff_email, is_active: form.is_active }
        if (form.password) {
          updates.password = form.password
        }
        await updateMutation.mutateAsync({ staffId: editingStaff.staff_id, updates })
        toast.success("Staff member updated.")
      } else if (sendInvite) {
        await createMutation.mutateAsync({ staff_name: form.staff_name, staff_email: form.staff_email, is_active: form.is_active, password: null })
        toast.success(`Invite sent to ${form.staff_email}.`)
      } else {
        await createMutation.mutateAsync(form)
        toast.success("Staff member added.")
      }
      onOpenChange(false)
    } catch {
      // error is captured in mutation.error and shown below
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditMode ? "Edit staff member" : "Add staff member"}</DialogTitle>
          <DialogDescription>
            {isEditMode
              ? "Update this staff member's details. Leave the password blank to keep it unchanged."
              : "Add a new staff member to this college."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="staff_name">Name</Label>
            <Input
              id="staff_name"
              required
              minLength={2}
              value={form.staff_name}
              onChange={(e) => setForm((f) => ({ ...f, staff_name: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="staff_email">Email</Label>
            <Input
              id="staff_email"
              type="email"
              required
              value={form.staff_email}
              onChange={(e) => setForm((f) => ({ ...f, staff_email: e.target.value }))}
            />
          </div>

          {!isEditMode && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={sendInvite}
                onChange={(e) => setSendInvite(e.target.checked)}
                className="size-4 rounded border-input accent-primary outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              />
              Email them a link to set their own password
            </label>
          )}

          {(isEditMode || !sendInvite) && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">{isEditMode ? "New password (optional)" : "Password"}</Label>
              <Input
                id="password"
                type="password"
                required={!isEditMode}
                minLength={8}
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                placeholder={isEditMode ? "Leave blank to keep current password" : "At least 8 characters"}
              />
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              className="size-4 rounded border-input accent-primary outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
            Active
          </label>

          {mutation.isError && (
            <p role="alert" className="text-sm text-destructive">
              {mutation.error?.message || "Something went wrong. Please try again."}
            </p>
          )}

          <DialogFooter>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Saving..." : isEditMode ? "Save changes" : sendInvite ? "Send invite" : "Add staff"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
