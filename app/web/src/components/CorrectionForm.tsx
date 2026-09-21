import type { CorrectionPayload, ResultRow, TaxonomyTheme } from "../api";
import { Button, Chip, Input, Select } from "../ui";

export const SENTIMENTS = ["Négatif", "Neutre", "Positif"];
// Valeur sentinelle de la liste déroulante : bascule le champ en saisie libre.
const OTHER = "__AUTRE__";
const OTHER_LABEL = "Autre (saisie manuelle)";

export interface ThemeDraft {
  niv1: string;
  niv2: string;
  sentiment: string;
  niv1Manual: boolean;
  niv2Manual: boolean;
}

export const emptyTheme = (): ThemeDraft => ({
  niv1: "", niv2: "", sentiment: "Neutre", niv1Manual: false, niv2Manual: false,
});

const norm = (s: string) => s.trim().toLowerCase();

/** Éditeur réutilisé pour le thème principal et le second thème. */
export function ThemeEditor({
  title, themes, value, onChange, onRemove,
}: {
  title: string;
  themes: TaxonomyTheme[];
  value: ThemeDraft;
  onChange: (next: ThemeDraft) => void;
  onRemove?: () => void;
}) {
  const childrenOf = (n1: string) =>
    themes.find((t) => norm(t.niv1) === norm(n1))?.niv2 ?? [];
  const canonNiv1 = (v: string) => themes.find((t) => norm(t.niv1) === norm(v))?.niv1;
  const niv2Options = childrenOf(value.niv1);
  const niv1IsOther = value.niv1Manual || (!!value.niv1 && canonNiv1(value.niv1) === undefined);
  const niv2IsOther = niv1IsOther || value.niv2Manual ||
    (!!value.niv2 && !niv2Options.some((c) => norm(c) === norm(value.niv2)));

  const onNiv1Select = (selected: string) => {
    if (selected === OTHER) {
      onChange({ ...value, niv1Manual: true, niv1: "", niv2Manual: true, niv2: "" });
      return;
    }
    const kids = childrenOf(selected);
    onChange({
      ...value,
      niv1Manual: false,
      niv1: selected,
      niv2Manual: false,
      niv2: kids.some((c) => norm(c) === norm(value.niv2)) ? value.niv2 : (kids[0] ?? ""),
    });
  };

  const onNiv2Select = (selected: string) => {
    if (selected === OTHER) onChange({ ...value, niv2Manual: true, niv2: "" });
    else onChange({ ...value, niv2Manual: false, niv2: selected });
  };

  return (
    <div className="ui-stack" style={{ gap: "var(--sp-3)", padding: "var(--sp-4)", border: "1px solid var(--cu-neutral-200)", borderRadius: "var(--r-lg)" }}>
      <div className="ui-row">
        <strong>{title}</strong>
        <div className="ui-spacer" />
        {onRemove && <Button variant="ghost" size="sm" onClick={onRemove}>Supprimer le second thème</Button>}
      </div>
      <div className="ui-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="ui-stack" style={{ gap: "var(--sp-2)" }}>
          <Select
            label="Thème niv.1"
            value={niv1IsOther ? OTHER : (canonNiv1(value.niv1) ?? value.niv1)}
            onChange={(e) => onNiv1Select(e.target.value)}
          >
            {themes.map((t) => <option key={t.niv1} value={t.niv1}>{t.niv1}</option>)}
            <option value={OTHER}>{OTHER_LABEL}</option>
          </Select>
          {niv1IsOther && (
            <Input
              aria-label={`Nouveau thème — ${title}`}
              placeholder="Saisir un nouveau thème"
              value={value.niv1}
              autoFocus={value.niv1Manual}
              autoComplete="off"
              onChange={(e) => onChange({ ...value, niv1: e.target.value })}
            />
          )}
        </div>

        <div className="ui-stack" style={{ gap: "var(--sp-2)" }}>
          <Select
            label="Sous-thème niv.2"
            value={niv2IsOther ? OTHER : (niv2Options.find((c) => norm(c) === norm(value.niv2)) ?? value.niv2)}
            onChange={(e) => onNiv2Select(e.target.value)}
          >
            {niv2Options.map((n) => <option key={n} value={n}>{n}</option>)}
            <option value={OTHER}>{OTHER_LABEL}</option>
          </Select>
          {niv2IsOther && (
            <Input
              aria-label={`Nouveau sous-thème — ${title}`}
              placeholder="Saisir un nouveau sous-thème"
              value={value.niv2}
              autoComplete="off"
              onChange={(e) => onChange({ ...value, niv2: e.target.value })}
            />
          )}
        </div>
      </div>
      <Select label={`Sentiment — ${title.toLowerCase()}`} value={value.sentiment}
              onChange={(e) => onChange({ ...value, sentiment: e.target.value })}>
        {SENTIMENTS.map((s) => <option key={s}>{s}</option>)}
      </Select>
    </div>
  );
}

/** Brouillon de correction complet : thème principal, second thème optionnel, signaux. */
export interface CorrectionDraft {
  primary: ThemeDraft;
  secondary: ThemeDraft;
  secondaryEnabled: boolean;
  sigR: boolean;
  sigC: boolean;
  sigI: boolean;
}

/** Initialise un brouillon à partir des valeurs actuelles d'un résultat. */
export function draftFromResult(item: ResultRow): CorrectionDraft {
  return {
    primary: {
      niv1: item.theme1_niv1 ?? "", niv2: item.theme1_niv2 ?? "",
      sentiment: item.theme1_sentiment ?? "Neutre", niv1Manual: false, niv2Manual: false,
    },
    secondary: {
      niv1: item.theme2_niv1 ?? "", niv2: item.theme2_niv2 ?? "",
      sentiment: item.theme2_sentiment ?? "Neutre", niv1Manual: false, niv2Manual: false,
    },
    secondaryEnabled: !!item.theme2_niv1,
    sigR: item.signal_rupture, sigC: item.signal_churn, sigI: item.signal_insatisfaction,
  };
}

/** Construit le payload envoyé à `PATCH /api/results/{id}` pour l'action donnée. */
export function buildCorrectionPayload(draft: CorrectionDraft, action: "validate" | "correct"): CorrectionPayload {
  if (action === "validate") return { action };
  return {
    action,
    theme1_niv1: draft.primary.niv1, theme1_niv2: draft.primary.niv2, theme1_sentiment: draft.primary.sentiment,
    theme2_niv1: draft.secondaryEnabled ? draft.secondary.niv1 : "",
    theme2_niv2: draft.secondaryEnabled ? draft.secondary.niv2 : "",
    theme2_sentiment: draft.secondaryEnabled ? draft.secondary.sentiment : "",
    signal_rupture: draft.sigR, signal_churn: draft.sigC, signal_insatisfaction: draft.sigI,
  };
}

/** Thème principal (et second thème s'il est activé) obligatoires avant envoi. */
export function isCorrectionValid(draft: CorrectionDraft): boolean {
  return !!draft.primary.niv1.trim() && !!draft.primary.niv2.trim() && !!draft.primary.sentiment &&
    (!draft.secondaryEnabled ||
      (!!draft.secondary.niv1.trim() && !!draft.secondary.niv2.trim() && !!draft.secondary.sentiment));
}

/**
 * Corps de formulaire complet (thème principal, second thème, signaux),
 * sans les actions de validation — laissées à l'appelant (Revue, Résultats)
 * dont les libellés et raccourcis diffèrent.
 */
export function CorrectionFields({
  themes, draft, onChange,
}: {
  themes: TaxonomyTheme[];
  draft: CorrectionDraft;
  onChange: (next: CorrectionDraft) => void;
}) {
  const enableSecondary = () => {
    const first = themes[0];
    onChange({
      ...draft,
      secondaryEnabled: true,
      secondary: first
        ? { niv1: first.niv1, niv2: first.niv2[0] ?? "", sentiment: "Neutre", niv1Manual: false, niv2Manual: false }
        : { ...emptyTheme(), niv1Manual: true, niv2Manual: true },
    });
  };
  const disableSecondary = () => onChange({ ...draft, secondaryEnabled: false, secondary: emptyTheme() });

  return (
    <>
      <ThemeEditor title="Thème principal" themes={themes} value={draft.primary}
                   onChange={(primary) => onChange({ ...draft, primary })} />

      {draft.secondaryEnabled ? (
        <ThemeEditor title="Second thème" themes={themes} value={draft.secondary}
                     onChange={(secondary) => onChange({ ...draft, secondary })}
                     onRemove={disableSecondary} />
      ) : (
        <div>
          <Button variant="secondary" size="sm" onClick={enableSecondary}>+ Ajouter un second thème</Button>
        </div>
      )}

      <div className="ui-field">
        <span className="ui-field__label">Signaux</span>
        <div className="ui-row ui-row--wrap">
          <Chip active={draft.sigR} onClick={() => onChange({ ...draft, sigR: !draft.sigR })}>Rupture client</Chip>
          <Chip active={draft.sigC} onClick={() => onChange({ ...draft, sigC: !draft.sigC })}>Churn</Chip>
          <Chip active={draft.sigI} onClick={() => onChange({ ...draft, sigI: !draft.sigI })}>Insatisfaction forte</Chip>
        </div>
      </div>
    </>
  );
}
