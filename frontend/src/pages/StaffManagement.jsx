import { useState } from "react"
import { Plus, Pencil, Trash2, Users, Search, Download, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { useAuth } from "@/context/AuthContext"
import { useCurrentCollege } from "@/context/CollegeContext"
import { useStaffList, useDeleteStaff, exportStaff } from "@/hooks/useStaff"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { StaffFormDialog } from "@/components/StaffFormDialog"
import { PaginationControls } from "@/components/PaginationControls"
import { TableSkeletonRows } from "@/components/TableSkeleton"
import { EmptyState, FilteredEmptyState } from "@/components/EmptyState"
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

const PAGE_SIZE = 15

export default function StaffManagement() {
  const { user } = useAuth()
  const { college, hasNoCollege } = useCurrentCollege()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingStaff, setEditingStaff] = useState(null)
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(1)
  const [isExporting, setIsExporting] = useState(false)
  const debouncedSearch = useDebouncedValue(search, 350)

  const [prevSearch, setPrevSearch] = useState(debouncedSearch)
  if (debouncedSearch !== prevSearch) {
    setPrevSearch(debouncedSearch)
    setPage(1)
  }

  const { data, isLoading, isFetching, isError, error } = useStaffList(college?.college_id, {
    page,
    pageSize: PAGE_SIZE,
    search: debouncedSearch,
  })
  const deleteMutation = useDeleteStaff(college?.college_id)

  const staff = data?.items || []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

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

  async function handleExport() {
    setIsExporting(true)
    try {
      await exportStaff(college.college_id, debouncedSearch)
    } catch (err) {
      toast.error(err?.message || "Failed to export. Please try again.")
    } finally {
      setIsExporting(false)
    }
  }

  if (hasNoCollege) {
    return (
      <EmptyState
        icon={Users}
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
          {(total > 0 || debouncedSearch) && (
            <div className="flex gap-2">
              <div className="relative w-full sm:w-56">
                <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search name or email..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-8"
                />
              </div>
              <Button variant="outline" size="icon" onClick={handleExport} disabled={isExporting} title="Export to CSV">
                {isExporting ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
              </Button>
            </div>
          )}
          <Button onClick={openCreateDialog} className="gap-2">
            <Plus className="size-4" />
            Add staff
          </Button>
        </div>
      </div>

      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error?.message || "Failed to load staff. Please try again."}
        </p>
      )}

      {!isLoading && !isError && total === 0 && !debouncedSearch && (
        <EmptyState icon={Users} title="No staff yet" description="Add the first staff member for this college." />
      )}

      {!isLoading && total === 0 && debouncedSearch && (
        <FilteredEmptyState query={debouncedSearch} onClear={() => setSearch("")} itemLabel="staff" />
      )}

      {(isLoading || staff.length > 0) && (
        <Table className={isFetching && !isLoading ? "opacity-60 transition-opacity" : undefined}>
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
              staff.map((member) => {
                const isSelf = member.staff_id === user?.staff_id
                return (
                  <TableRow key={member.staff_id}>
                    <TableCell>
                      <span className="font-medium">{member.staff_name}</span>
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
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openEditDialog(member)}
                          aria-label={`Edit ${member.staff_name}`}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        {/* Self-delete is only blocked here in the UI - the backend
                            doesn't stop you from deleting your own account, so this
                            button is a safety net, not the real enforcement. */}
                        {!isSelf && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDelete(member)}
                            aria-label={`Remove ${member.staff_name}`}
                          >
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

