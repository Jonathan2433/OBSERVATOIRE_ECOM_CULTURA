import { useEffect, useState, type FormEvent } from "react";
import { createUser, deactivateUser, listUsers, updateUser, type Role, type User } from "../api";
import { useAuth } from "../auth";

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
      <h1>Gestion des utilisateurs</h1>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "2rem" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #ddd" }}>
            <th style={{ padding: "0.4rem" }}>Identifiant</th>
            <th>Rôle</th>
            <th>Statut</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "0.4rem" }}>{u.username}{u.id === me?.id && " (vous)"}</td>
              <td>{u.role}</td>
              <td style={{ color: u.is_active ? "green" : "#999" }}>{u.is_active ? "actif" : "désactivé"}</td>
              <td>
                {u.id !== me?.id && (
                  <button onClick={() => toggleActive(u)}>
                    {u.is_active ? "Désactiver" : "Réactiver"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Créer un compte</h3>
      <form onSubmit={onCreate} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
        <input
          placeholder="Identifiant" value={form.username} required
          onChange={(e) => setForm({ ...form, username: e.target.value })}
        />
        <input
          type="password" placeholder="Mot de passe (≥ 12 car.)" value={form.password} required minLength={12}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
          <option value="analyste">analyste</option>
          <option value="admin">admin</option>
        </select>
        <button type="submit">Créer</button>
      </form>
    </div>
  );
}
