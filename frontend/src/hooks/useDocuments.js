import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api, ApiError } from "@/lib/api"

export function useDocuments(collegeId) {
  return useQuery({
    queryKey: ["documents", collegeId],
    queryFn: async () => {
      try {
        return await api.get(`/router/colleges/${collegeId}/documents`)
      } catch (err) {
        // Same pattern as staff/students/queue - 404 means "none yet", not an error.
        if (err instanceof ApiError && err.status === 404) {
          return []
        }
        throw err
      }
    },
    enabled: !!collegeId,
    // Poll while any document is still processing, so status flips to
    // success/failed without the user having to refresh. Stop polling once
    // everything has settled, to not hammer the backend forever.
    refetchInterval: (query) => {
      const docs = query.state.data
      if (!docs) return false
      return docs.some((d) => d.status === "processing") ? 4000 : false
    },
  })
}

export function useUploadDocument(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file) => {
      const formData = new FormData()
      formData.append("file", file)
      return api.postFormData(`/router/colleges/${collegeId}/documents`, formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", collegeId] })
    },
  })
}

export function useDeleteDocument(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId) => api.delete(`/router/colleges/${collegeId}/documents/${documentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", collegeId] })
    },
  })
}

export function useRetryDocument(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId) => api.post(`/router/colleges/${collegeId}/documents/${documentId}/retry`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", collegeId] })
    },
  })
}

// Not a query - the signed URL is short-lived, so we fetch it fresh at the
// moment the person actually wants to view the file rather than caching it.
export function fetchDocumentUrl(collegeId, documentId) {
  return api.get(`/router/colleges/${collegeId}/documents/${documentId}/url`)
}
