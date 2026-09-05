import { toast } from "sonner"
import { Label } from "@/components/ui/label"
import { useStaffList } from "@/hooks/useStaff"
import { useAssignStudent } from "@/hooks/useStudents"

export function AssignStaffSelect({ collegeId, studentId, assignedTo }) {
  // page_size caps at 100 server-side - fine for a single-college staff
  // roster in a dropdown; this mirrors how the staff list page itself pages.
  const { data: staffData, isLoading: staffLoading } = useStaffList(collegeId, { pageSize: 100 })
  const assignMutation = useAssignStudent(collegeId, studentId)

  async function handleChange(e) {
    const value = e.target.value
    const staffId = value === "" ? null : Number(value)
    try {
      await assignMutation.mutateAsync(staffId)
      toast.success(staffId ? "Student assigned." : "Student unassigned.")
    } catch {
      toast.error(assignMutation.error?.message || "Failed to update assignment.")
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="assigned-to">Assigned to</Label>
      <select
        id="assigned-to"
        value={assignedTo ?? ""}
        onChange={handleChange}
        disabled={staffLoading || assignMutation.isPending}
        className="border-input flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <option value="">Unassigned</option>
        {staffData?.items?.map((staff) => (
          <option key={staff.staff_id} value={staff.staff_id}>
            {staff.staff_name}
          </option>
        ))}
      </select>
    </div>
  )
}
