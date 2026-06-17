import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", color: "#1a1a1a" }}>
      <header
        style={{
          display: "flex", alignItems: "center", gap: "1.5rem",
          padding: "0.75rem 1.5rem", borderBottom: "1px solid #e3e3e3", background: "#fafafa",
        }}
      >
        <strong style={{ fontSize: "1.05rem" }}>Observatoire Ecom Studio</strong>
        <nav style={{ display: "flex", gap: "1rem", flex: 1 }}>
          <Link to="/">Accueil</Link>
          <Link to="/lots">Lots</Link>
          <Link to="/test">Test à la volée</Link>
          {user?.role === "admin" && <Link to="/admin/users">Utilisateurs</Link>}
        </nav>
        <span style={{ color: "#666", fontSize: ".9rem" }}>
          {user?.username} · <em>{user?.role}</em>
        </span>
        <button onClick={onLogout} style={{ cursor: "pointer" }}>Déconnexion</button>
      </header>
      <main style={{ maxWidth: 960, margin: "2rem auto", padding: "0 1.5rem" }}>
        <Outlet />
      </main>
    </div>
  );
}
