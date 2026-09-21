import { useEffect, useState } from "react";
import type { ThemeSentimentView } from "../api";
import {
  rankThemeLabels, valuesForThemeCriterion, type ThemeRankingCriterion,
} from "../themeSentimentSort";
import BarList from "./BarList";
import { Card, Chip, InfoTip } from "../ui";

type ThemeAngle = "principal" | "mentions";

export interface ThemeDistributionData {
  themes: Record<string, number>;
  subthemes: Record<string, number>;
  hierarchy: Record<string, Record<string, number>>;
  sentiment: ThemeSentimentView;
}

export interface ThemeDistributionPanelProps {
  totalVerbatims: number;
  nBiThemes: number;
  principal: ThemeDistributionData;
  mentions: ThemeDistributionData;
  secondary: ThemeDistributionData;
}

function ThemeLevelGrid({
  data,
  selectedNiv1,
  onSelect,
  ranking,
  color = "var(--cu-primary-500)",
}: {
  data: ThemeDistributionData;
  selectedNiv1: string | null;
  onSelect: (theme: string | null) => void;
  ranking: ThemeRankingCriterion;
  color?: string;
}) {
  const displayedSubthemeVolumes = selectedNiv1
    ? data.hierarchy[selectedNiv1] ?? {}
    : data.subthemes;
  const displayedSubthemeSentiments = selectedNiv1
    ? data.sentiment.hierarchy[selectedNiv1] ?? {}
    : data.sentiment.subthemes;
  const themeValues = valuesForThemeCriterion(data.themes, data.sentiment.themes, ranking);
  const subthemeValues = valuesForThemeCriterion(
    displayedSubthemeVolumes, displayedSubthemeSentiments, ranking,
  );
  const themeOrder = rankThemeLabels(data.themes, data.sentiment.themes, ranking);
  const subthemeOrder = rankThemeLabels(
    displayedSubthemeVolumes, displayedSubthemeSentiments, ranking,
  );
  const sentimentColor = ranking === "Négatif"
    ? "var(--cu-sentiment-negatif)"
    : ranking === "Neutre"
      ? "var(--cu-sentiment-neutre)"
      : ranking === "Positif"
        ? "var(--cu-sentiment-positif)"
        : null;

  useEffect(() => {
    if (selectedNiv1 && !(selectedNiv1 in data.themes)) onSelect(null);
  }, [data.themes, onSelect, selectedNiv1]);

  return (
    <div className="ui-grid theme-distribution__levels">
      <Card
        title="Niveau 1"
        actions={<InfoTip text="Sélectionnez un thème pour limiter le tableau Niveau 2 à ses sous-thèmes." />}
      >
        <BarList
          data={themeValues}
          order={themeOrder}
          color={sentimentColor ?? color}
          selectedKey={selectedNiv1}
          onSelect={(theme) => onSelect(selectedNiv1 === theme ? null : theme)}
          ariaLabel="Filtrer les sous-thèmes par thème de niveau 1"
          showZeroValues={ranking !== "volume" && Object.keys(data.sentiment.themes).length > 0}
        />
      </Card>
      <Card
        title="Niveau 2 (sous-thèmes)"
        actions={selectedNiv1
          ? <Chip onClick={() => onSelect(null)}>Afficher tous</Chip>
          : undefined}
      >
        {selectedNiv1 && (
          <p className="theme-drilldown__context">
            Sous-thèmes rattachés à <strong>{selectedNiv1}</strong>.
          </p>
        )}
        <BarList
          data={subthemeValues}
          order={subthemeOrder}
          color={sentimentColor ?? "var(--cu-primary-300)"}
          showZeroValues={ranking !== "volume" && Object.keys(displayedSubthemeSentiments).length > 0}
        />
      </Card>
    </div>
  );
}

/**
 * Répartition hiérarchique commune aux tableaux de bord d'un lot et global.
 *
 * Les angles restent explicitement séparés : le principal compte une voix par
 * verbatim, tandis que les mentions additionnent les thèmes de rang 1 et 2.
 */
export default function ThemeDistributionPanel({
  totalVerbatims,
  nBiThemes,
  principal,
  mentions,
  secondary,
}: ThemeDistributionPanelProps) {
  const [angle, setAngle] = useState<ThemeAngle>("mentions");
  const [ranking, setRanking] = useState<ThemeRankingCriterion>("volume");
  const [selectedNiv1, setSelectedNiv1] = useState<string | null>(null);
  const [selectedSecondaryNiv1, setSelectedSecondaryNiv1] = useState<string | null>(null);
  const activeDistribution = angle === "mentions" ? mentions : principal;
  const nMentions = Object.values(mentions.themes).reduce((sum, count) => sum + count, 0);

  return (
    <>
      <Card title="Répartition des thèmes" actions={(
        <span className="ui-row theme-distribution__actions">
          <Chip active={angle === "principal"} onClick={() => setAngle("principal")}>
            Thème principal
          </Chip>
          <Chip active={angle === "mentions"} onClick={() => setAngle("mentions")}>
            Toutes mentions
          </Chip>
          <InfoTip text="« Thème principal » compte une voix par verbatim. « Toutes mentions » ajoute le second thème : la somme dépasse alors le nombre de verbatims, ce qui est normal." />
        </span>
      )}>
        <div className="ui-stack">
          <p className="ui-muted">
            {angle === "mentions"
              ? `${nMentions} mention(s) de thème pour ${totalVerbatims} verbatim(s), dont ${nBiThemes} bi-thème(s).`
              : "Thème de tête de chaque verbatim classé."}
          </p>
          <div className="theme-distribution__sort" role="group" aria-label="Classer les thèmes par">
            <span className="theme-distribution__sort-label">Classer par</span>
            <span className="ui-row theme-distribution__sort-options">
              <Chip active={ranking === "volume"} onClick={() => setRanking("volume")}>
                Volume total
              </Chip>
              <Chip active={ranking === "Négatif"} onClick={() => setRanking("Négatif")}>
                Négatifs
              </Chip>
              <Chip active={ranking === "Neutre"} onClick={() => setRanking("Neutre")}>
                Neutres
              </Chip>
              <Chip active={ranking === "Positif"} onClick={() => setRanking("Positif")}>
                Positifs
              </Chip>
            </span>
            <InfoTip text="Le classement est décroissant. Les barres et les valeurs affichent le volume total ou le nombre absolu de mentions du sentiment choisi. Les thèmes à zéro restent visibles en bas de liste." />
          </div>
          <ThemeLevelGrid
            data={activeDistribution}
            selectedNiv1={selectedNiv1}
            onSelect={setSelectedNiv1}
            ranking={ranking}
          />
        </div>
      </Card>

      <Card
        title="Second thème seul"
        actions={<InfoTip text="Ce que la vue « thème principal » rend invisible : les sujets évoqués en appui, jamais en tête." />}
      >
        {nBiThemes === 0 ? (
          <p className="ui-muted">Aucun verbatim du périmètre ne porte de second thème.</p>
        ) : (
          <ThemeLevelGrid
            data={secondary}
            selectedNiv1={selectedSecondaryNiv1}
            onSelect={setSelectedSecondaryNiv1}
            ranking={ranking}
            color="var(--cu-primary-300)"
          />
        )}
      </Card>
    </>
  );
}
