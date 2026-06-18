import { useState } from "react";
import {
  Badge, Button, Card, Chip, Dialog, Drawer, EmptyState, FileDropzone,
  Input, ProgressBar, Select, Spinner, StatCard, Textarea,
} from "../ui";

/** Vitrine du design system (référence vivante). Route /design. */
export default function DesignShowcase() {
  const [loading, setLoading] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [chip, setChip] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  const primaries = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900"];
  const neutrals = ["0", "50", "100", "200", "300", "400", "500", "600", "700", "800", "900"];

  return (
    <div className="ui-stack" style={{ maxWidth: "var(--layout-content-max)", margin: "0 auto", padding: "var(--sp-6)" }}>
      <div>
        <h1>Design system — Observatoire Ecom Studio</h1>
        <p className="ui-muted">Référence vivante des tokens et composants (V2). Charte : docs/CHARTE_UI_V2.md.</p>
      </div>

      <Card title="Couleurs — Primaire (turquoise Cultura)">
        <div className="ui-row ui-row--wrap">
          {primaries.map((s) => (
            <Swatch key={s} name={`primary-${s}`} varName={`--cu-primary-${s}`} />
          ))}
        </div>
      </Card>

      <Card title="Couleurs — Neutres">
        <div className="ui-row ui-row--wrap">
          {neutrals.map((s) => (
            <Swatch key={s} name={`neutral-${s}`} varName={`--cu-neutral-${s}`} />
          ))}
        </div>
      </Card>

      <Card title="Boutons">
        <div className="ui-row ui-row--wrap">
          <Button variant="primary">Primaire</Button>
          <Button variant="secondary">Secondaire</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="primary" size="sm">Petit</Button>
          <Button variant="primary" disabled>Désactivé</Button>
          <Button variant="primary" loading={loading} onClick={() => { setLoading(true); setTimeout(() => setLoading(false), 1200); }}>
            {loading ? "Chargement…" : "Tester le chargement"}
          </Button>
        </div>
      </Card>

      <Card title="Badges (statuts, sentiments, signaux)">
        <div className="ui-row ui-row--wrap">
          <Badge tone="neutral">En attente</Badge>
          <Badge tone="info" dot>En cours</Badge>
          <Badge tone="success" dot>Terminé</Badge>
          <Badge tone="warning" dot>En revue</Badge>
          <Badge tone="danger" dot>Échec</Badge>
          <Badge tone="primary">Corrigé</Badge>
        </div>
      </Card>

      <Card title="Indicateurs (StatCard)">
        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <StatCard label="Verbatims traités" value="11 247" hint="dernier lot" />
          <StatCard label="En revue" value="8,3 %" hint="934 verbatims" />
          <StatCard label="Erreurs" value="0" />
          <StatCard label="Durée" value="42 min" hint="≈ 0,22 s/verbatim" />
        </div>
      </Card>

      <Card title="Champs de formulaire">
        <div className="ui-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <Input label="Identifiant" placeholder="prénom.nom" hint="Compte interne" />
          <Input label="Champ en erreur" defaultValue="valeur" error="Ce champ est invalide." />
          <Select label="Sentiment"><option>Négatif</option><option>Neutre</option><option>Positif</option></Select>
          <Textarea label="Verbatim" placeholder="Saisir un texte…" />
        </div>
      </Card>

      <Card title="Progression, chips, dépôt de fichier">
        <div className="ui-stack">
          <ProgressBar value={62} />
          <ProgressBar indeterminate showLabel={false} />
          <div className="ui-row ui-row--wrap">
            <Chip active={chip} onClick={() => setChip(!chip)}>Filtre activable</Chip>
            <Chip>Inactif</Chip>
          </div>
          <FileDropzone label="Fichier MDTC" file={file} onSelect={setFile} />
        </div>
      </Card>

      <Card title="Surcouches (Drawer, Dialog)">
        <div className="ui-row ui-row--wrap">
          <Button variant="secondary" onClick={() => setDrawer(true)}>Ouvrir un panneau</Button>
          <Button variant="danger" onClick={() => setDialog(true)}>Ouvrir une confirmation</Button>
        </div>
        <Drawer open={drawer} title="Panneau de détail" onClose={() => setDrawer(false)}>
          <p>Contenu du panneau latéral. Ferme sur Échap, clic hors zone, ou ×.</p>
        </Drawer>
        <Dialog open={dialog} title="Confirmer l'action ?" danger
                confirmLabel="Confirmer" onConfirm={() => setDialog(false)} onCancel={() => setDialog(false)}>
          <p>Exemple de modale de confirmation danger.</p>
        </Dialog>
      </Card>

      <Card title="États (chargement, vide)">
        <div className="ui-stack">
          <Spinner label="Chargement des résultats…" />
          <EmptyState
            title="Aucun lot pour le moment"
            description="Déposez deux fichiers Excel pour lancer un premier traitement."
            action={<Button variant="primary">Nouveau lot</Button>}
          />
        </div>
      </Card>
    </div>
  );
}

function Swatch({ name, varName }: { name: string; varName: string }) {
  return (
    <div style={{ width: 92 }}>
      <div style={{
        height: 44, borderRadius: "var(--r-sm)", background: `var(${varName})`,
        border: "1px solid var(--cu-border)",
      }} />
      <div style={{ fontSize: "var(--fs-xs)", marginTop: 4 }} className="ui-mono">{name}</div>
    </div>
  );
}
