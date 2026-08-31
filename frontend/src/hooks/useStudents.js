import { useQuery } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useStudentList(collegeId) {
  return useQuery({
    queryKey: ["students", collegeId],
    queryFn: async () => {
      try {
        return await api.get(`/router/students/${collegeId}`)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return []
        }
        throw err
      }
    },
    enabled: !!collegeId,
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
