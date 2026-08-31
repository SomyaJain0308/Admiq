import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { AuthProvider } from "@/context/AuthContext"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { DashboardLayout } from "@/components/DashboardLayout"
import Login from "@/pages/Login"
import DashboardHome from "@/pages/DashboardHome"
import LowConfidenceQueue from "@/pages/LowConfidenceQueue"
import StaffManagement from "@/pages/StaffManagement"
import StudentsList from "@/pages/StudentsList"
import StudentDetail from "@/pages/StudentDetail"
import CollegeSettings from "@/pages/CollegeSettings"
import NotFound from "@/pages/NotFound"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <Toaster richColors position="top-right" />
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route element={<ProtectedRoute />}>
                <Route element={<DashboardLayout />}>
                  <Route path="/" element={<DashboardHome />} />
                  <Route path="/queue" element={<LowConfidenceQueue />} />
                  <Route path="/staff" element={<StaffManagement />} />
                  <Route path="/students" element={<StudentsList />} />
                  <Route path="/students/:studentId" element={<StudentDetail />} />
                  <Route path="/settings" element={<CollegeSettings />} />
                </Route>
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
