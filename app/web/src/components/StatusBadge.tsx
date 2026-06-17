const COLORS: Record<string, { bg: string; fg: string; label: string }> = {
  pending: { bg: "#eee", fg: "#555", label: "en attente" },
  running: { bg: "#e3f0ff", fg: "#0b5cad", label: "en cours" },
  done: { bg: "#e3f7e8", fg: "#1a7f37", label: "terminé" },
  failed: { bg: "#fdecea", fg: "#b3261e", label: "échec" },
  canceled: { bg: "#f3f3f3", fg: "#888", label: "annulé" },
};

export default function StatusBadge({ status }: { status: string }) {
  const c = COLORS[status] ?? { bg: "#eee", fg: "#333", label: status };
  return (
    <span style={{ background: c.bg, color: c.fg, padding: "0.1rem 0.5rem", borderRadius: 12, fontSize: ".8rem", fontWeight: 600 }}>
      {c.label}
    </span>
  );
}
