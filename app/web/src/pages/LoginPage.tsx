import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de connexion");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 360, margin: "6rem auto", padding: "0 1rem" }}>
      <h1 style={{ fontSize: "1.3rem" }}>Observatoire Ecom Studio</h1>
      <p style={{ color: "#666", marginTop: 0 }}>Connexion</p>
      <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <input
          placeholder="Identifiant" value={username} autoFocus
          onChange={(e) => setUsername(e.target.value)} required
        />
        <input
          type="password" placeholder="Mot de passe" value={password}
          onChange={(e) => setPassword(e.target.value)} required
        />
        {error && <p style={{ color: "crimson", margin: 0 }}>{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "Connexion…" : "Se connecter"}</button>
      </form>
    </div>
  );
}
