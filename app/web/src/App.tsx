import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setError(String(e)));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", maxWidth: 680, margin: "4rem auto", padding: "0 1rem" }}>
      <h1 style={{ marginBottom: 0 }}>Observatoire Ecom Studio</h1>
      <p style={{ color: "#555" }}>Classification &amp; pilotage des verbatims clients Cultura.</p>

      {error && <p style={{ color: "crimson" }}>API injoignable : {error}</p>}
      {!health && !error && <p>Connexion à l'API…</p>}
      {health && (
        <ul>
          <li>État global : <b>{health.status}</b></li>
          <li>Version API : {health.version} ({health.env})</li>
          <li>
            Base de données : <b>{health.components?.database ? "OK" : "KO"}</b> ·{" "}
            Redis : <b>{health.components?.redis ? "OK" : "KO"}</b>
          </li>
        </ul>
      )}

      <footer style={{ marginTop: "3rem", color: "#999", fontSize: ".85rem" }}>
        V1 — squelette (lot L0)
      </footer>
    </main>
  );
}
