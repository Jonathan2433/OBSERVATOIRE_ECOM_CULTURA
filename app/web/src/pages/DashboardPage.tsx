import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth, type Health } from "../api";
import { useAuth } from "../auth";
import { Badge, Card, StatCard } from "../ui";

function statusBadge(ok: boolean | undefined) {
  return ok ? <Badge tone="success" dot>OK</Badge> : <Badge tone="danger" dot>KO</Badge>;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setErr(true));
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Bienvenue, {user?.username}</h1>
        <p className="page-header__sub">Plateforme de classification et de pilotage des verbatims clients Cultura.</p>
      </div>

      <div className="ui-stack">
        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
          <StatCard label="API" value={err ? "Injoignable" : (health?.status ?? "…")} hint={health ? `v${health.version}` : undefined} />
          <StatCard label="Base de données" value={statusBadge(health?.components?.database)} />
          <StatCard label="File de traitement" value={statusBadge(health?.components?.redis)} hint="Redis" />
        </div>

        <Card title="Démarrer">
          <div className="ui-row ui-row--wrap">
            <Link className="ui-btn ui-btn--primary ui-btn--md" to="/lots">Traiter un nouveau lot</Link>
            <Link className="ui-btn ui-btn--secondary ui-btn--md" to="/tableaux-de-bord">Tableaux de bord</Link>
            <Link className="ui-btn ui-btn--secondary ui-btn--md" to="/test">Test à la volée</Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
