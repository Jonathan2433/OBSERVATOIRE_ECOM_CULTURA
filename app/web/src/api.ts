// Client API minimal (L0). Étoffé au fil des lots (auth, lots, résultats…).

export interface Health {
  status: string;
  app: string;
  version: string;
  env?: string;
  components?: Record<string, boolean>;
}

export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`API a répondu ${res.status}`);
  return res.json();
}
