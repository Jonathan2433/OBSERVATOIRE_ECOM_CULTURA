import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import UsersPage from "./pages/UsersPage";
import BatchesPage from "./pages/BatchesPage";
import BatchDetailPage from "./pages/BatchDetailPage";

function Spinner() {
  return <p style={{ fontFamily: "system-ui", margin: "4rem", textAlign: "center" }}>Chargement…</p>;
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
          <Route path="lots/:id" element={<BatchDetailPage />} />
          <Route path="admin/users" element={<RequireAdmin><UsersPage /></RequireAdmin>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
