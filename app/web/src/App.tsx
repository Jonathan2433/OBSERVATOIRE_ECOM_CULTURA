import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import UsersPage from "./pages/UsersPage";
import BatchesPage from "./pages/BatchesPage";
import BatchDetailPage from "./pages/BatchDetailPage";
import ResultsPage from "./pages/ResultsPage";
import ReviewPage from "./pages/ReviewPage";
import BatchKpiPage from "./pages/BatchKpiPage";
import DashboardsPage from "./pages/DashboardsPage";
import AdminPage from "./pages/AdminPage";
import TestPage from "./pages/TestPage";
import DesignShowcase from "./pages/DesignShowcase";
import ProfilePage from "./pages/ProfilePage";
import AidePage from "./pages/AidePage";
import { Spinner as UISpinner } from "./ui";

function Spinner() {
  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "60vh" }}>
      <UISpinner label="Chargement…" />
    </div>
  );
}

function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return user ? <Outlet /> : <Navigate to="/login" replace />;
}

function RequireAdmin({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  return user?.role === "admin" ? children : <Navigate to="/" replace />;
}

function LoginRoute() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return user ? <Navigate to="/" replace /> : <LoginPage />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="lots" element={<BatchesPage />} />
          <Route path="lots/:id" element={<BatchDetailPage />}>
            <Route index element={<BatchKpiPage />} />
            <Route path="resultats" element={<ResultsPage />} />
            <Route path="revue" element={<ReviewPage />} />
            <Route path="kpi" element={<Navigate to=".." replace />} />
          </Route>
          <Route path="tableaux-de-bord" element={<DashboardsPage />} />
          <Route path="test" element={<TestPage />} />
          <Route path="design" element={<DesignShowcase />} />
          <Route path="compte" element={<ProfilePage />} />
          <Route path="aide" element={<AidePage />} />
          <Route path="admin/users" element={<RequireAdmin><UsersPage /></RequireAdmin>} />
          <Route path="admin" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
