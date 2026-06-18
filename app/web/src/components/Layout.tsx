import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../auth";
import { Button } from "../ui";

/* --- Icônes SVG inline (offline, sans dépendance) --- */
const icon = (path: ReactNode) => (
  <svg className="app-nav__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{path}</svg>
);
const IconHome = icon(<><path d="M3 11l9-8 9 8" /><path d="M5 10v10h14V10" /></>);
const IconLots = icon(<><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>);
const IconChart = icon(<><path d="M3 3v18h18" /><path d="M7 14l3-3 3 3 4-5" /></>);
const IconTest = icon(<><path d="M10 2v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V2" /><path d="M8 2h8" /></>);
const IconUsers = icon(<><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0" /><path d="M16 6a3 3 0 0 1 0 6" /><path d="M21 20a6 6 0 0 0-4-5.6" /></>);
const IconCog = icon(<><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></>);

interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean }
const MAIN: NavItem[] = [
  { to: "/", label: "Accueil", icon: IconHome, end: true },
  { to: "/lots", label: "Lots", icon: IconLots },
  { to: "/tableaux-de-bord", label: "Tableaux de bord", icon: IconChart },
  { to: "/test", label: "Test à la volée", icon: IconTest },
];
const ADMIN: NavItem[] = [
  { to: "/admin/users", label: "Utilisateurs", icon: IconUsers },
  { to: "/admin", label: "Administration", icon: IconCog, end: true },
];

/* --- Fil d'Ariane dérivé de l'URL --- */
const CRUMB_LABELS: Record<string, string> = {
  lots: "Lots", "tableaux-de-bord": "Tableaux de bord", test: "Test à la volée",
  admin: "Administration", users: "Utilisateurs", resultats: "Résultats",
  revue: "Revue", kpi: "Tableau de bord", design: "Design",
};
function useCrumbs() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const crumbs: { label: string; to: string }[] = [];
  let acc = "";
  for (const p of parts) {
    acc += `/${p}`;
    const label = CRUMB_LABELS[p] ?? (/^\d+$/.test(p) ? `Lot ${p}` : p);
    crumbs.push({ label, to: acc });
  }
  return crumbs;
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const crumbs = useCrumbs();

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const navClass = ({ isActive }: { isActive: boolean }) =>
    "app-nav__item" + (isActive ? " is-active" : "");

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">
          <span className="app-brand__name">Observatoire</span>
          <span className="app-brand__sub">Ecom Studio · Cultura</span>
        </div>
        <nav className="app-nav" aria-label="Navigation principale">
          {MAIN.map((it) => (
            <NavLink key={it.to} to={it.to} end={it.end} className={navClass}>
              {it.icon}<span>{it.label}</span>
            </NavLink>
          ))}
          {user?.role === "admin" && (
            <>
              <div className="app-nav__group">Administration</div>
              {ADMIN.map((it) => (
                <NavLink key={it.to} to={it.to} end={it.end} className={navClass}>
                  {it.icon}<span>{it.label}</span>
                </NavLink>
              ))}
            </>
          )}
        </nav>
      </aside>

      <header className="app-topbar">
        <nav className="app-crumbs" aria-label="Fil d'Ariane">
          <Link to="/">Accueil</Link>
          {crumbs.map((c, i) => (
            <span key={c.to} className="ui-row">
              <span className="app-crumbs__sep">/</span>
              {i === crumbs.length - 1
                ? <span className="app-crumbs__current">{c.label}</span>
                : <Link to={c.to}>{c.label}</Link>}
            </span>
          ))}
        </nav>
        <div className="ui-spacer" />
        <span className="app-user">{user?.username} · <b>{user?.role}</b></span>
        <Button variant="secondary" size="sm" onClick={onLogout}>Déconnexion</Button>
      </header>

      <main className="app-content">
        <div className="app-content__inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
