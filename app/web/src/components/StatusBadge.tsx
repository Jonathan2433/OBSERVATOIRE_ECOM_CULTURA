import { Badge, type BadgeTone } from "../ui";

const MAP: Record<string, { tone: BadgeTone; label: string }> = {
  pending: { tone: "neutral", label: "en attente" },
  running: { tone: "info", label: "en cours" },
  done: { tone: "success", label: "terminé" },
  failed: { tone: "danger", label: "échec" },
  canceled: { tone: "neutral", label: "annulé" },
};

export default function StatusBadge({ status }: { status: string }) {
  const c = MAP[status] ?? { tone: "neutral" as BadgeTone, label: status };
  const dot = status === "running" || status === "done" || status === "failed";
  return <Badge tone={c.tone} dot={dot}>{c.label}</Badge>;
}
