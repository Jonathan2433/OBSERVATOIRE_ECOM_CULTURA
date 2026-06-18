import { useEffect, useState, type FormEvent } from "react";
import { createUser, deactivateUser, listUsers, updateUser, type Role, type User } from "../api";
import { useAuth } from "../auth";
import { Badge, Button, Card, Input, Select } from "../ui";

export default function UsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ username: string; password: string; role: Role }>({
    username: "", password: "", role: "analyste",
  });

  const refresh = () => listUsers().then(setUsers).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => { refresh(); }, []);

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await createUser(form.username.trim(), form.password, form.role);
      setForm({ username: "", password: "", role: "analyste" });
      refresh();
    } catch (err: any) {
      setError(err?.message ?? "Erreur");
    }
  };

  const toggleActive = async (u: User) => {
    setError(null);
    try {
      if (u.is_active) await deactivateUser(u.id);
      else await updateUser(u.id, { is_active: true });
      refresh();
    } catch (err: any) {
      setError(err?.message ?? "Erreur");
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Utilisateurs</h1>
        <p className="page-header__sub">Comptes locaux et rôles (analyste / admin).</p>
      </div>

      {error && <p className="ui-field__error">{error}</p>}

      <div className="ui-stack">
        <Card title="Comptes">
          <div className="ui-table-wrap">
            <table className="ui-table">
              <thead>
                <tr><th>Identifiant</th><th>Rôle</th><th>Statut</th><th></th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.username}{u.id === me?.id && <span className="ui-muted"> (vous)</span>}</td>
                    <td><Badge tone={u.role === "admin" ? "primary" : "neutral"}>{u.role}</Badge></td>
                    <td>{u.is_active ? <Badge tone="success" dot>actif</Badge> : <Badge tone="neutral">désactivé</Badge>}</td>
                    <td style={{ textAlign: "right" }}>
                      {u.id !== me?.id && (
                        <Button variant={u.is_active ? "secondary" : "primary"} size="sm" onClick={() => toggleActive(u)}>
                          {u.is_active ? "Désactiver" : "Réactiver"}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Créer un compte">
          <form onSubmit={onCreate} className="ui-toolbar" style={{ alignItems: "flex-end" }}>
            <Input label="Identifiant" placeholder="prénom.nom" value={form.username} required
                   onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <Input label="Mot de passe (≥ 12 car.)" type="password" value={form.password} required minLength={12}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <Select label="Rôle" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              <option value="analyste">analyste</option>
              <option value="admin">admin</option>
            </Select>
            <Button type="submit" variant="primary">Créer</Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
