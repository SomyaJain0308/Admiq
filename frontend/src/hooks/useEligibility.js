import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

export function useCourses(collegeId) {
  return useQuery({
    queryKey: ["courses", collegeId],
    queryFn: () => api.get(`/router/colleges/${collegeId}/courses`),
    enabled: !!collegeId,
  })
}

export function useCourse(collegeId, courseId) {
  return useQuery({
    queryKey: ["courses", collegeId, courseId],
    queryFn: () => api.get(`/router/colleges/${collegeId}/courses/${courseId}`),
    enabled: !!collegeId && !!courseId,
  })
}

export function useCreateCourse(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ courseName, parentCourseId } = {}) =>
      api.post(`/router/colleges/${collegeId}/courses`, { course_name: courseName, parent_course_id: parentCourseId ?? null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId] })
    },
  })
}

export function useUpdateCourse(collegeId, courseId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patch) => api.patch(`/router/colleges/${collegeId}/courses/${courseId}`, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId] })
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId, courseId] })
    },
  })
}

export function useDeleteCourse(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId) => api.delete(`/router/colleges/${collegeId}/courses/${courseId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId] })
    },
  })
}

export function useCreateRule(collegeId, courseId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ruleType, config }) => api.post(`/router/colleges/${collegeId}/courses/${courseId}/rules`, { rule_type: ruleType, config }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId, courseId] })
    },
  })
}

export function useUpdateRule(collegeId, courseId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ruleId, patch }) => api.patch(`/router/colleges/${collegeId}/courses/${courseId}/rules/${ruleId}`, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId, courseId] })
    },
  })
}

export function useDeleteRule(collegeId, courseId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ruleId) => api.delete(`/router/colleges/${collegeId}/courses/${courseId}/rules/${ruleId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId, courseId] })
    },
  })
}

export function useReorderRules(collegeId, courseId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ruleIds) => api.post(`/router/colleges/${collegeId}/courses/${courseId}/rules/reorder`, { rule_ids: ruleIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["courses", collegeId, courseId] })
    },
  })
}

export function usePreviewCourse(collegeId, courseId, enabled) {
  return useQuery({
    queryKey: ["courses", collegeId, courseId, "preview"],
    queryFn: () => api.get(`/router/colleges/${collegeId}/courses/${courseId}/preview`),
    enabled: !!collegeId && !!courseId && !!enabled,
  })
}

export function useRuleConflicts(collegeId, courseId, enabled) {
  return useQuery({
    queryKey: ["courses", collegeId, courseId, "rule-conflicts"],
    queryFn: () => api.get(`/router/colleges/${collegeId}/courses/${courseId}/rule-conflicts`),
    enabled: !!collegeId && !!courseId && !!enabled,
  })
}

export function useEligibilityAnalytics(collegeId) {
  return useQuery({
    queryKey: ["eligibility-analytics", collegeId],
    queryFn: () => api.get(`/router/colleges/${collegeId}/eligibility-analytics`),
    enabled: !!collegeId,
  })
}
