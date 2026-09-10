import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, useParams } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { AuthProvider } from "@/context/AuthContext"
import { CollegeProvider } from "@/context/CollegeContext"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { DashboardLayout } from "@/components/DashboardLayout"
import { PageLoader } from "@/components/PageLoader"

// Login is on the initial, unauthenticated path almost everyone hits first,
// so it stays in the main bundle. Everything behind auth is route-split so a
// fresh login doesn't have to download StudentDetail/DocumentsPage/charts
// before the dashboard shell can render.
import Login from "@/pages/Login"
const ForgotPassword = lazy(() => import("@/pages/ForgotPassword"))
const ResetPassword = lazy(() => import("@/pages/ResetPassword"))
const DashboardHome = lazy(() => import("@/pages/DashboardHome"))
const LowConfidenceQueue = lazy(() => import("@/pages/LowConfidenceQueue"))
const StaffManagement = lazy(() => import("@/pages/StaffManagement"))
const StudentsList = lazy(() => import("@/pages/StudentsList"))
const StudentDetail = lazy(() => import("@/pages/StudentDetail"))
const CollegeSettings = lazy(() => import("@/pages/CollegeSettings"))
const DocumentsPage = lazy(() => import("@/pages/DocumentsPage"))
const NotFound = lazy(() => import("@/pages/NotFound"))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

// /students/:studentId is the one route where the URL changes (a different
// studentId) without React Router unmounting anything - navigating from one
// student to another keeps the same <ErrorBoundary> instance mounted. Without
// this wrapper, a crash on student A's page would leave the boundary stuck
// showing "Something went wrong" even after navigating to student B's
// (perfectly fine) page, since the boundary's hasError state only resets on
// remount. Keying it to studentId forces that remount on every param change.
function StudentDetailRoute() {
  const { studentId } = useParams()
  return (
    <ErrorBoundary key={studentId} fullScreen={false}>
      <StudentDetail />
    </ErrorBoundary>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename="/home">
          <AuthProvider>
            <CollegeProvider>
              <Toaster richColors position="top-right" />
              <Suspense fallback={<PageLoader />}>
                <Routes>
                  <Route path="/login" element={<ErrorBoundary fullScreen={false}><Login /></ErrorBoundary>} />
                  <Route path="/forgot-password" element={<ErrorBoundary fullScreen={false}><ForgotPassword /></ErrorBoundary>} />
                  <Route path="/reset-password" element={<ErrorBoundary fullScreen={false}><ResetPassword /></ErrorBoundary>} />
                  <Route element={<ProtectedRoute />}>
                    <Route element={<DashboardLayout />}>
                      {/* Each page gets its own boundary here (rather than one
                          around <Outlet/> in DashboardLayout) so a crash is
                          caught before it unmounts the layout itself - the
                          sidebar, nav, and college switcher stay usable and
                          the person can navigate away from the broken page. */}
                      <Route path="/" element={<ErrorBoundary fullScreen={false}><DashboardHome /></ErrorBoundary>} />
                      <Route path="/queue" element={<ErrorBoundary fullScreen={false}><LowConfidenceQueue /></ErrorBoundary>} />
                      <Route path="/staff" element={<ErrorBoundary fullScreen={false}><StaffManagement /></ErrorBoundary>} />
                      <Route path="/students" element={<ErrorBoundary fullScreen={false}><StudentsList /></ErrorBoundary>} />
                      <Route path="/students/:studentId" element={<StudentDetailRoute />} />
                      <Route path="/documents" element={<ErrorBoundary fullScreen={false}><DocumentsPage /></ErrorBoundary>} />
                      <Route path="/settings" element={<ErrorBoundary fullScreen={false}><CollegeSettings /></ErrorBoundary>} />
                    </Route>
                  </Route>
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </CollegeProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
