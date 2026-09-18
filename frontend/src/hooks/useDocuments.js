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

export function useViewDocument(collegeId) {
  return useMutation({
    mutationFn: async (documentId) => {
      const { url } = await api.get(`/router/colleges/${collegeId}/documents/${documentId}/view-url`)
      return url
    },
    onSuccess: (url) => {
      // Signed URL is short-lived (5 min) and scoped to this one file -
      // open immediately rather than storing it anywhere.
      window.open(url, "_blank", "noopener,noreferrer")
    },
  })
}

export function useRetryDocument(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId) => api.post(`/router/colleges/${collegeId}/documents/${documentId}/retry`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", collegeId] })
    },
  })
}

export function useDeleteDocument(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId) => api.delete(`/router/colleges/${collegeId}/documents/${documentId}`),
    onMutate: async (documentId) => {
      const queryKey = ["documents", collegeId]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData(queryKey)
      queryClient.setQueryData(queryKey, (old) => (old ? old.filter((d) => d.document_id !== documentId) : old))
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["documents", collegeId], context.previous)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", collegeId] })
    },
  })
}

// Bulk delete: one request to the batch endpoint rather than N parallel
// single-deletes. Optimistically clears every selected row up front, then
// rolls back only the ones the server reports it didn't actually delete
// (not_found_ids - e.g. already removed by someone else) so a partial
// outcome doesn't make successfully-deleted rows reappear.
export function useBulkDeleteDocuments(collegeId) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (documentIds) => {
      const result = await api.post(`/router/colleges/${collegeId}/documents/bulk-delete`, { document_ids: documentIds })
      return { failedIds: result.not_found_ids, succeededCount: result.deleted_ids.length }
    },
    onMutate: async (documentIds) => {
      const queryKey = ["documents", collegeId]
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData(queryKey)
      const idSet = new Set(documentIds)
      queryClient.setQueryData(queryKey, (old) => (old ? old.filter((d) => !idSet.has(d.document_id)) : old))
      return { previous }
    },
    onError: (_err, _vars, context) => {
      // The whole request failed (network error, 4xx/5xx) - nothing was
      // deleted server-side, so restore everything that was optimistically
      // removed.
      if (context?.previous) queryClient.setQueryData(["documents", collegeId], context.previous)
    },
    onSuccess: (result, _vars, context) => {
      if (result.failedIds.length > 0 && context?.previous) {
        // Put back only the rows the server says it didn't delete.
        const failedSet = new Set(result.failedIds)
        const stillFailed = context.previous.filter((d) => failedSet.has(d.document_id))
        queryClient.setQueryData(["documents", collegeId], (old) => [...(old || []), ...stillFailed])
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", collegeId] })
    },
  })
}
