import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useStudentList(collegeId, { page = 1, pageSize = 20, search = "", assignedTo = "" } = {}) {
  return useQuery({
    queryKey: ["students", collegeId, page, pageSize, search, assignedTo],
    queryFn: () => {
      const params = new URLSearchParams({ page, page_size: pageSize })
      if (search) params.set("search", search)
      if (assignedTo) params.set("assigned_to", assignedTo)
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
    // Keep the thread live while someone's actually looking at it - a
    // student can message again on WhatsApp at any moment, and staff
    // shouldn't have to close and reopen the page/dialog to see it land.
    // Only runs while this query is actually mounted (student detail page
    // or the reply dialog), and React Query already pauses polling when
    // the tab isn't visible.
    refetchInterval: 8_000,
  })
}

export function useMessageStudent(collegeId, studentId) {
  const queryClient = useQueryClient()
  return useMutation({
    // content is either a plain string (existing callers, save_as_answer
    // stays off) or { content, saveAsAnswer, expiresAt } for callers that
    // want the opt-in - kept as one hook rather than a second one, since
    // it's the same endpoint either way.
    mutationFn: (input) => {
      const { content, saveAsAnswer = false, expiresAt = null } =
        typeof input === "string" ? { content: input } : input
      return api.post(`/router/students/${collegeId}/${studentId}/message`, {
        content,
        save_as_answer: saveAsAnswer,
        expires_at: expiresAt,
      })
    },
    // The conversation view reads from the "conversation" query cache, so
    // once the message is saved, refetch it - otherwise the staff member's
    // own message wouldn't show up in the thread until some unrelated
    // refetch happened to fire.
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["conversation", collegeId, studentId] })
      // A save-as-answer message resolves into the same table the queue's
      // "Resolved" tab reads from, so that list is stale until this
      // refetches too.
      if (result?.saved_as_answer) {
        queryClient.invalidateQueries({ queryKey: ["low-confidence-queries", collegeId] })
      }
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
