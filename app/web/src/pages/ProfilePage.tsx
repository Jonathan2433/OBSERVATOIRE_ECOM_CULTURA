import { useState, type FormEvent } from "react";
import { changePassword } from "../api";
import { useAuth } from "../auth";
import { Badge, Button, Card, Input } from "../ui";

export default function ProfilePage() {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null); setError(null);
    if (next !== confirm) { setError("La confirmation ne correspond pas."); return; }
    if (next.length < 12) { setError("Le nouveau mot de passe doit faire au moins 12 caractères."); return; }
    setBusy(true);
    try {
      await changePassword(current, next);
      setMsg("Mot de passe changé.");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err: any) {
      setError(err?.message ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Mon compte</h1>
        <p className="page-header__sub">{user?.username} · <Badge tone={user?.role === "admin" ? "primary" : "neutral"}>{user?.role}</Badge></p>
      </div>

      {msg && <p style={{ color: "var(--cu-success)" }}>{msg}</p>}
      {error && <p className="ui-field__error">{error}</p>}

      <Card title="Changer mon mot de passe">
        <form onSubmit={onSubmit} className="ui-stack" style={{ maxWidth: 360 }}>
          <Input label="Mot de passe actuel" type="password" value={current} autoComplete="current-password"
                 onChange={(e) => setCurrent(e.target.value)} required />
          <Input label="Nouveau mot de passe (≥ 12 car.)" type="password" value={next} autoComplete="new-password"
                 onChange={(e) => setNext(e.target.value)} required minLength={12} />
          <Input label="Confirmer le nouveau mot de passe" type="password" value={confirm} autoComplete="new-password"
                 onChange={(e) => setConfirm(e.target.value)} required />
          <div><Button type="submit" variant="primary" loading={busy}>Enregistrer</Button></div>
        </form>
      </Card>
    </div>
  );
}
