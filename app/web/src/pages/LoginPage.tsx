import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Button, Card, Input } from "../ui";

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
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-brand__name">Observatoire Ecom Studio</div>
          <div className="auth-brand__sub">Pilotage des verbatims clients Cultura</div>
        </div>
        <Card title="Connexion">
          <form onSubmit={onSubmit} className="ui-stack">
            <Input
              label="Identifiant" placeholder="prénom.nom" value={username} autoFocus
              autoComplete="username" onChange={(e) => setUsername(e.target.value)} required
            />
            <Input
              label="Mot de passe" type="password" placeholder="••••••••" value={password}
              autoComplete="current-password" onChange={(e) => setPassword(e.target.value)}
              required error={error ?? undefined}
            />
            <Button type="submit" variant="primary" loading={busy} style={{ width: "100%" }}>
              {busy ? "Connexion…" : "Se connecter"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
