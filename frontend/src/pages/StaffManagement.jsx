import { useMemo, useState } from "react"
import { Plus, Pencil, Trash2, Users, Search } from "lucide-react"
import { toast } from "sonner"
import { useAuth } from "@/context/AuthContext"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useStaffList, useDeleteStaff } from "@/hooks/useStaff"
import { usePagination } from "@/hooks/usePagination"
import { StaffFormDialog } from "@/components/StaffFormDialog"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table"

export default function StaffManagement() {
  const { user } = useAuth()
  const { college, hasNoCollege } = useCurrentCollege()
  const { data: staff, isLoading, isError, error } = useStaffList(college?.college_id)
  const deleteMutation = useDeleteStaff(college?.college_id)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingStaff, setEditingStaff] = useState(null)
  const [search, setSearch] = useState("")

  const filteredStaff = useMemo(() => {
    if (!staff) return []
    const query = search.trim().toLowerCase()
    if (!query) return staff
    return staff.filter(
      (s) => s.staff_name?.toLowerCase().includes(query) || s.staff_email?.toLowerCase().includes(query)
    )
  }, [staff, search])

  const { page, setPage, totalPages, pageItems } = usePagination(filteredStaff, 15)

  function openCreateDialog() {
    setEditingStaff(null)
    setDialogOpen(true)
  }

  function openEditDialog(staffMember) {
    setEditingStaff(staffMember)
    setDialogOpen(true)
  }

  async function handleDelete(staffMember) {
    const confirmed = window.confirm(`Remove ${staffMember.staff_name} from this college? This can't be undone.`)
    if (!confirmed) return
    try {
      await deleteMutation.mutateAsync(staffMember.staff_id)
      toast.success(`${staffMember.staff_name} removed.`)
    } catch (err) {
      toast.error(err?.message || "Failed to remove staff member.")
    }
  }

  if (hasNoCollege) {
    return (
      <EmptyState
        title="No college access yet"
        description="Your account isn't linked to a college yet. Contact an admin to get set up."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Staff</h1>
          <p className="text-muted-foreground">Manage who has access to {college.college_name}.</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          {staff?.length > 0 && (
            <div className="relative w-full sm:w-56">
              <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search name or email..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
              />
            </div>
          )}
          <Button onClick={openCreateDialog} className="gap-2">
            <Plus className="size-4" />
            Add staff
          </Button>
        </div>
      </div>

      {isError && (
        <p className="text-sm text-destructive">
          {error?.message || "Failed to load staff. Please try again."}
        </p>
      )}

      {!isLoading && !isError && staff?.length === 0 && (
        <EmptyState title="No staff yet" description="Add the first staff member for this college." />
      )}

      {!isLoading && staff?.length > 0 && filteredStaff.length === 0 && (
        <p className="text-sm text-muted-foreground">No staff match "{search}".</p>
      )}

      {(isLoading || pageItems.length > 0) && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-32"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableSkeletonRows columns={4} />
            ) : (
              pageItems.map((member) => {
                const isSelf = member.staff_id === user?.staff_id
                return (
                  <TableRow key={member.staff_id}>
                    <TableCell>
                      {member.staff_name}
                      {isSelf && <span className="ml-2 text-xs text-muted-foreground">(you)</span>}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{member.staff_email}</TableCell>
                    <TableCell>
                      <Badge variant={member.is_active ? "default" : "secondary"}>
                        {member.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="icon" onClick={() => openEditDialog(member)}>
                          <Pencil className="size-4" />
                        </Button>
                        {/* Self-delete is only blocked here in the UI - the backend
                            doesn't stop you from deleting your own account, so this
                            button is a safety net, not the real enforcement. */}
                        {!isSelf && (
                          <Button variant="ghost" size="icon" onClick={() => handleDelete(member)}>
                            <Trash2 className="size-4 text-destructive" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      )}

      {!isLoading && <PaginationControls page={page} totalPages={totalPages} onPageChange={setPage} />}

      <StaffFormDialog
        collegeId={college?.college_id}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editingStaff={editingStaff}
      />
    </div>
  )
}

function EmptyState({ title, description }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
      <Users className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
    </div>
  )
}
