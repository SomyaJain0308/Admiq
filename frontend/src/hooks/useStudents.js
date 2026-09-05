import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useStudentList(collegeId, { page = 1, pageSize = 20, search = "" } = {}) {
  return useQuery({
    queryKey: ["students", collegeId, page, pageSize, search],
    queryFn: () => {
      const params = new URLSearchParams({ page, page_size: pageSize })
      if (search) params.set("search", search)
      return api.get(`/router/students/${collegeId}?${params.toString()}`)
    },
    enabled: !!collegeId,
    // Keeps showing the previous page's data (rather than a loading flash)
    // while the next page/search result comes in - the list count and page
    // number update as soon as the request lands.
    placeholderData: keepPreviousData,
  })
}

export function useStudentDetail(collegeId, studentId) {
  return useQuery({
    queryKey: ["student", collegeId, studentId],
    queryFn: () => api.get(`/router/students/${collegeId}/${studentId}`),
    enabled: !!collegeId && !!studentId,
  })
}

export function useConversation(collegeId, studentId) {
  return useQuery({
    queryKey: ["conversation", collegeId, studentId],
    queryFn: async () => {
      try {
        return await api.get(`/router/students/view_convo/${collegeId}/${studentId}`)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return []
        }
        throw err
      }
    },
    enabled: !!collegeId && !!studentId,
  })
}

export function useMessageStudent(collegeId, studentId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content) => api.post(`/router/students/${collegeId}/${studentId}/message`, { content }),
    // The conversation view reads from the "conversation" query cache, so
    // once the message is saved, refetch it - otherwise the staff member's
    // own message wouldn't show up in the thread until some unrelated
    // refetch happened to fire.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversation", collegeId, studentId] })
    },
  })
}

export function useUpdateStudentNotes(collegeId, studentId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (internalNotes) => api.patch(`/router/students/${collegeId}/${studentId}/notes`, { internal_notes: internalNotes }),
    onSuccess: () => {
      // Also invalidates the list ("students", collegeId, ...) - not just
      // this one detail record - in case a notes preview ever shows up
      // there too.
      queryClient.invalidateQueries({ queryKey: ["student", collegeId, studentId] })
      queryClient.invalidateQueries({ queryKey: ["students", collegeId] })
    },
  })
}

export function useAssignStudent(collegeId, studentId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (assignedTo) => api.patch(`/router/students/${collegeId}/${studentId}/assign`, { assigned_to: assignedTo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["student", collegeId, studentId] })
      queryClient.invalidateQueries({ queryKey: ["students", collegeId] })
    },
  })
}

export function exportStudents(collegeId, search = "") {
  const params = new URLSearchParams()
  if (search) params.set("search", search)
  const query = params.toString()
  return api.downloadFile(`/router/students/${collegeId}/export${query ? `?${query}` : ""}`)
}
