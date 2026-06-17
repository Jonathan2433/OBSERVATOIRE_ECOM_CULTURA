import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth, type Health } from "../api";
import { useAuth } from "../auth";

export default function DashboardPage() {
  const { user } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div>
      <h1>Bienvenue, {user?.username}</h1>
      <p style={{ color: "#666" }}>
        Plateforme de classification et de pilotage des verbatims clients Cultura.
      </p>

      <section style={{ marginTop: "2rem", padding: "1rem 1.25rem", border: "1px solid #eee", borderRadius: 8 }}>
        <h3 style={{ marginTop: 0 }}>État du système</h3>
        {health ? (
          <ul>
            <li>API : <b>{health.status}</b> (v{health.version})</li>
            <li>Base de données : <b>{health.components?.database ? "OK" : "KO"}</b></li>
            <li>File de traitement (Redis) : <b>{health.components?.redis ? "OK" : "KO"}</b></li>
          </ul>
        ) : (
          <p style={{ color: "crimson" }}>API injoignable.</p>
        )}
      </section>

      <p style={{ marginTop: "2rem" }}>
        <Link to="/lots">→ Traiter un nouveau lot de verbatims</Link>
      </p>
      <p style={{ color: "#999", fontSize: ".9rem" }}>
        Les modules « Résultats », « Revue » et « Tableaux de bord » arriveront aux lots suivants (L4 → L6).
      </p>
    </div>
  );
}
