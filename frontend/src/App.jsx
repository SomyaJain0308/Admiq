import { BrowserRouter, Routes, Route } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { AuthProvider } from "@/context/AuthContext"
import { CollegeProvider } from "@/context/CollegeContext"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { DashboardLayout } from "@/components/DashboardLayout"
import Login from "@/pages/Login"
import ForgotPassword from "@/pages/ForgotPassword"
import ResetPassword from "@/pages/ResetPassword"
import DashboardHome from "@/pages/DashboardHome"
import LowConfidenceQueue from "@/pages/LowConfidenceQueue"
import StaffManagement from "@/pages/StaffManagement"
import StudentsList from "@/pages/StudentsList"
import StudentDetail from "@/pages/StudentDetail"
import CollegeSettings from "@/pages/CollegeSettings"
import DocumentsPage from "@/pages/DocumentsPage"
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
        <BrowserRouter basename="/app">
          <AuthProvider>
            <CollegeProvider>
              <Toaster richColors position="top-right" />
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/forgot-password" element={<ForgotPassword />} />
                <Route path="/reset-password" element={<ResetPassword />} />
                <Route element={<ProtectedRoute />}>
                  <Route element={<DashboardLayout />}>
                    <Route path="/" element={<DashboardHome />} />
                    <Route path="/queue" element={<LowConfidenceQueue />} />
                    <Route path="/staff" element={<StaffManagement />} />
                    <Route path="/students" element={<StudentsList />} />
                    <Route path="/students/:studentId" element={<StudentDetail />} />
                    <Route path="/documents" element={<DocumentsPage />} />
                    <Route path="/settings" element={<CollegeSettings />} />
                  </Route>
                </Route>
                <Route path="*" element={<NotFound />} />
              </Routes>
            </CollegeProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
