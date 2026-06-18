# Charte UI/UX — Observatoire Ecom Studio (V2)

> **But de la V2** : transformer une V1 fonctionnelle (interface technique, styles
> *inline*) en une application **claire, professionnelle et agréable pour le métier**,
> sans rien changer aux fonctionnalités ni aux garde-fous. La V2 est une **couche de
> design**, pas une refonte fonctionnelle.

Statut : document de conception (choix validés). Mise en œuvre découpée dans
[`PLAN_V2_DESIGN.md`](PLAN_V2_DESIGN.md).

---

## 1. Décisions structurantes (validées)

| Sujet | Choix | Pourquoi |
|---|---|---|
| Approche technique | **Design-tokens CSS maison** + composants React réutilisables | Zéro nouvelle dépendance, **100 % offline**, build inchangé, fidèle à l'ethos du projet (§10 #1) |
| Palette | **Turquoise Cultura** comme primaire, déclinée ; tokens ajustables | Identité Cultura ; les hex sont centralisés (1 fichier à changer si charte officielle fournie) |
| Ambition | **Refonte complète, desktop-first** | App de travail mono-poste ; on optimise le poste analyste/admin |
| Langue | **Français**, ton sobre et direct | Public métier interne |

**Non-objectifs** : pas de nouvelle fonctionnalité, pas de dépendance runtime (pas de
CDN, pas de webfont téléchargée), pas de changement d'API ni de modèle de données.

---

## 2. Principes de design

1. **Clarté avant décoration** — chaque écran a une intention unique, lisible en 3 s.
2. **Une action principale par écran** — bouton primaire turquoise, le reste en secondaire/discret.
3. **Densité maîtrisée** — tables lisibles (zebra, en-têtes collants), espaces réguliers (échelle 4 px).
4. **Cohérence** — mêmes composants partout (boutons, badges, cartes, états vides/chargement/erreur).
5. **Confiance & transparence** — toujours afficher score de confiance + statut (auto / en revue / corrigé) ; jamais présenter une prédiction comme une vérité (cahier §10 #6).
6. **Accessibilité** — contraste AA, focus visible, navigation clavier, cibles ≥ 40 px.
7. **Sobriété de marque** — turquoise Cultura en accent et identité, fond neutre, pas de surcharge.

---

## 3. Fondations (design tokens)

Tous les tokens vivent dans **`src/styles/tokens.css`** (variables CSS `:root`).
Changer la charte = éditer ce fichier. Aucun hex en dur dans les composants.

### 3.1 Couleurs — Primaire (turquoise Cultura)

> Valeurs **de travail** ancrées sur le turquoise/bleu canard Cultura. À remplacer
> par les hex officiels si la charte graphique est fournie (1 token = 1 ligne).

| Token | Hex | Usage |
|---|---|---|
| `--cu-primary-50` | `#E6F5F6` | fonds très clairs, surbrillance |
| `--cu-primary-100` | `#C3E8EA` | survol léger, puces |
| `--cu-primary-300` | `#54BBC2` | bordures actives, graphes |
| `--cu-primary-500` | `#008C99` | **couleur primaire** (boutons, liens, sélection) |
| `--cu-primary-600` | `#007B87` | survol bouton primaire |
| `--cu-primary-700` | `#006670` | texte sur fond clair, en-têtes de marque |
| `--cu-primary-900` | `#003B41` | bandeau latéral foncé (option) |

### 3.2 Couleurs — Neutres (gris ardoise)

`--cu-neutral-0 #FFFFFF` · `-50 #F7F8F9` · `-100 #EEF0F2` · `-200 #E1E4E8` ·
`-300 #CBD1D8` · `-400 #9AA3AD` · `-500 #6B7682` · `-600 #4B5560` ·
`-700 #353D46` · `-800 #232930` · `-900 #14181D`

Rôles : fond app `--cu-neutral-50`, surfaces/cartes `--cu-neutral-0`, bordures
`--cu-neutral-200`, texte principal `--cu-neutral-800`, texte secondaire `--cu-neutral-500`.

### 3.3 Couleurs — Sémantiques & métier

| Rôle | Texte | Fond | Usage |
|---|---|---|---|
| Succès | `#1A7F37` | `#E7F4EC` | lot terminé, validé |
| Avertissement | `#B7791F` | `#FBF1E0` | en revue, seuil proche |
| Danger | `#C0392B` | `#FBE9E7` | erreur, purge, échec |
| Info | `--cu-primary-700` | `--cu-primary-50` | en cours, neutre |

**Sentiments** (harmonisés, repris de la V1) : Négatif `#D64545` · Neutre `#9AA0A6` · Positif `#1A7F37`.
**Signaux** : rupture client → *danger* · churn → *avertissement* · insatisfaction forte → *orange* `#E08A2B`.

### 3.4 Typographie

- **Pile système** (aucun téléchargement, offline strict) :
  `-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
  *(Option ultérieure : auto-héberger « Inter » en local si une typo de marque est souhaitée — sans CDN.)*
- Échelle : `--fs-xs 12` · `sm 13` · `base 14` · `md 16` · `lg 20` · `xl 26` · `2xl 32` (px).
- Poids : 400 (corps), 500 (libellés), 600 (titres), 700 (chiffres clés). Interligne 1.5 corps / 1.25 titres.

### 3.5 Espacement, rayons, ombres

- **Espacement** (base 4 px) : `--sp-1 4` … `--sp-2 8` · `3 12` · `4 16` · `6 24` · `8 32` · `12 48`.
- **Rayons** : `--r-sm 6` · `--r-md 10` · `--r-lg 14` · `--r-pill 999`.
- **Ombres** : `--sh-1` (cartes, `0 1px 2px rgba(20,24,29,.06)`) · `--sh-2` (menus/modales) · `--sh-focus` (anneau focus turquoise).
- **Layout** : largeur de contenu max ~1200 px ; barre latérale 240 px ; topbar 56 px.

---

## 4. Bibliothèque de composants (à construire dans `src/ui/`)

Chaque composant est **piloté par les tokens**, typé, accessible, sans dépendance.

| Composant | Rôle | Notes clés |
|---|---|---|
| `AppShell` | Cadre : **barre latérale** (nav) + topbar (user, rôle, déconnexion) + zone contenu | Nav filtrée par rôle ; item actif surligné turquoise |
| `Button` | Actions | variantes `primary` / `secondary` / `ghost` / `danger` ; tailles `sm`/`md` ; état `loading` |
| `Card` / `Section` | Surfaces, regroupements | titre + actions optionnelles |
| `StatCard` | Tuile KPI (chiffre + libellé + tendance) | accent turquoise, flèche tendance |
| `Table` | Tables de données | en-tête collant, zebra, tri, pagination, densité réglable |
| `Badge` / `Tag` | Statuts, sentiments, signaux | mappés sur les couleurs sémantiques/métier |
| `ProgressBar` | Progression de lot | % + libellé, animé pendant le traitement |
| `Input` / `Select` / `Textarea` | Formulaires | label, aide, erreur, focus visible |
| `FileDropzone` | Dépôt des 2 Excel | glisser-déposer, validation, nom/taille, retrait |
| `Toast` | Notifications (fin de lot, erreurs, succès) | non bloquant, coin écran |
| `Dialog` | Confirmations (purge, désactivation compte) | focus-trap, action danger explicite |
| `Drawer` | Détail d'un verbatim (panneau latéral) | ouvre depuis la table Résultats |
| `Tabs`, `Breadcrumb` | Navigation secondaire | fil d'Ariane Lots → lot → résultats |
| `EmptyState`, `Spinner`, `Skeleton` | États vides / chargement | message + action suggérée |
| `Charts` (`BarList`, `StackedSentimentBar`, `Donut`, `Sparkline`) | Dataviz SVG maison | re-stylés sur tokens, légendes, accessibles |

---

## 5. Navigation cible

Passage de la **barre de menu horizontale** à une **barre latérale gauche** (pattern
« studio » data, plus lisible et extensible) :

```
┌───────────┬──────────────────────────────────────────────┐
│ CULTURA   │  Topbar : fil d'Ariane · admin · rôle · ⎋     │
│ Observat. ├──────────────────────────────────────────────┤
│           │                                              │
│ ▸ Accueil │   Zone de contenu (cartes, tables, dataviz)  │
│ ▸ Lots    │                                              │
│ ▸ Tableaux│                                              │
│ ▸ Test    │                                              │
│ ─ Admin ─ │   (section Admin visible pour le rôle admin) │
│ ▸ Compte  │                                              │
│ ▸ Config  │                                              │
└───────────┴──────────────────────────────────────────────┘
```

- Section **Admin** séparée visuellement, affichée uniquement pour le rôle `admin`.
- Item actif : fond `--cu-primary-50`, barre turquoise à gauche, texte `--cu-primary-700`.

---

## 6. Intentions par écran

| Écran | Avant (V1) | Cible V2 |
|---|---|---|
| **Connexion** | Formulaire brut centré | Page épurée, logo/typo de marque, carte centrée, message d'erreur clair, état *chargement* |
| **Accueil** | Liste à puces « État système » + note périmée | Tuiles **StatCard** (état API/DB/Redis, dernier lot, % en revue) + accès rapides en boutons |
| **Lots (liste)** | Table minimale | Table riche (statut en **Badge**, barre de progression inline, date, modèle, actions) + bouton primaire « Nouveau lot » |
| **Nouveau lot** | 2 champs fichier | **FileDropzone** ×2 (MDTC/Mopinion) avec validation visuelle, réglage du seuil, récapitulatif avant lancement |
| **Détail lot** | Texte de statut | En-tête avec **Badge** statut + **ProgressBar** + métadonnées en cartes + raccourcis (Résultats, Revue, KPI) |
| **Résultats** | Table dense + filtres bruts | Barre de filtres en **chips**, **Table** triable/paginée, **Drawer** de détail verbatim, exports en boutons, états vides |
| **Revue** | Formulaire séquentiel | **Mode focus** : une carte verbatim, sélecteurs niv.1/niv.2 contraints, raccourcis clavier, progression dans la file |
| **Tableaux de bord** | Listes de KPI + barres | Grille de **StatCard** + **Charts** stylés (thèmes, sentiments, thème×sentiment, tendances) + alertes seuils modèle |
| **Test à la volée** | Champ + JSON | Saisie + **carte de prédiction** lisible (thèmes, sentiment, signaux, confiance, badge modèle) |
| **Utilisateurs** | Table + formulaire | **Table** + **Dialog** création/édition, badges rôle/état |
| **Administration** | 3 sections empilées | **Tabs** (Configuration · Rétention · Audit) ; purge en **Dialog** de confirmation danger ; audit en table filtrable |

---

## 7. Contraintes transverses

- **Offline strict** : aucun asset externe (police système, icônes en SVG inline ou set local léger, pas de CDN). Cohérent §10 #1.
- **Accessibilité (cible AA)** : contraste texte ≥ 4.5:1, focus visible partout, libellés de formulaire, navigation clavier, `aria-*` sur composants interactifs.
- **Performance** : CSS tokens (pas de CSS-in-JS lourd) ; tables paginées ; rendu < 3 s/écran, filtre < 2 s (exigence §8).
- **Compatibilité** : Safari/Chrome desktop récents (poste cible).
- **Mode sombre** : *hors périmètre V2* (tokens conçus pour le permettre plus tard sans refonte).
- **Aucune régression** : routes, RBAC, appels API et garde-fous inchangés ; la recette V1 (`recette_v1.py`) doit rester verte.

---

## 8. Définition de « terminé » pour la V2

- [ ] `src/styles/tokens.css` centralise 100 % des couleurs/typo/espacements ; **0 hex en dur** dans les composants.
- [ ] Toutes les pages utilisent l'`AppShell` et la bibliothèque `src/ui/`.
- [ ] Cohérence visuelle : mêmes boutons/badges/tables/états partout.
- [ ] Contraste AA et focus visible vérifiés sur les écrans clés.
- [ ] Build Vite OK, type-check TS strict OK, **recette V1 toujours 48/48** (aucune régression fonctionnelle).
- [ ] Palette ajustable en 1 fichier ; documentation à jour.
