# Plan de développement V2 — Couche design UI/UX

Mise en œuvre de la [`CHARTE_UI_V2.md`](CHARTE_UI_V2.md). Même cadence que la V1 :
**1 lot = 1 branche `design/N-nom` = 1 incrément revu = 1 porte de validation PO**,
merge `--no-ff` sur `main` après validation. Suivi vivant dans `SUIVI_LOTS.md`.

> Règle d'or : **aucune régression fonctionnelle**. À chaque lot, `npm run build` +
> `tsc --noEmit` OK et la recette V1 (`app/tests/recette_v1.py`) reste **48/48**.

---

## Vue d'ensemble des lots

| Lot | Objet | Réf. charte | Taille |
|---|---|---|---|
| **D0** | Fondations : tokens, reset global, primitives, page vitrine | §3, §4 | M |
| **D1** | AppShell : barre latérale + topbar + fil d'Ariane (+ Connexion, Accueil) | §5, §6 | M |
| **D2** | Lots & ingestion : liste, **FileDropzone**, détail/progression | §6 | M |
| **D3** | Résultats & exports : filtres en chips, Table, Drawer détail | §6 | M |
| **D4** | Revue humaine : mode focus + raccourcis | §6 | S |
| **D5** | Tableaux de bord & dataviz : StatCards + charts stylés + alertes seuils | §6 | M |
| **D6** | Administration & comptes : Tabs, Dialogs, tables | §6 | S |
| **D7** | Finition, accessibilité (AA) & recette UI | §7, §8 | S |

Chemin critique : **D0 → D1**, puis D2…D6 (indépendants par écran, séquencés par 1 dev) → **D7** (recette).

---

## D0 — Fondations du design system
**Objectif** : poser le socle réutilisable, sans encore toucher les écrans métier.
**Contenu**
- `src/styles/tokens.css` (couleurs, typo, espacements, rayons, ombres) + `reset.css` + `global.css` ; import dans `main.tsx`.
- Primitives `src/ui/` : `Button`, `Card`/`Section`, `Badge`, `Input`/`Select`/`Textarea`, `Spinner`, `EmptyState`.
- Page **vitrine** `/design` (dev) présentant tokens + composants (référence vivante, pas de Storybook).
- Helpers : conventions de classes, typage des variantes.
**Livrable** : composants de base affichés sur `/design`, build OK.
**Acceptation** : 0 hex en dur dans les primitives ; tout dérive des tokens ; `tsc` + build verts.

## D1 — AppShell, navigation & écrans d'entrée
**Objectif** : le cadre applicatif et les 2 premiers écrans.
**Contenu**
- `AppShell` : **barre latérale** (nav filtrée par rôle, item actif turquoise), **topbar** (fil d'Ariane, user/rôle, déconnexion).
- Remplacement du `Layout` horizontal actuel.
- **Connexion** : carte centrée, identité de marque, erreurs/états.
- **Accueil** : tuiles `StatCard` (API/DB/Redis, dernier lot, % en revue) + accès rapides.
**Livrable** : navigation complète habillée, connexion + accueil refondus.
**Acceptation** : RBAC respecté dans la nav ; responsive desktop propre ; focus clavier OK.

## D2 — Lots & ingestion
**Contenu**
- **Liste des lots** : `Table` (statut en `Badge`, `ProgressBar` inline, date, modèle, actions), bouton primaire « Nouveau lot ».
- **Nouveau lot** : `FileDropzone` ×2 (MDTC/Mopinion) avec validation visuelle (format, taille), réglage du seuil, récap avant lancement.
- **Détail lot** : en-tête statut + `ProgressBar` + métadonnées en cartes + raccourcis (Résultats/Revue/KPI) ; `Toast` de fin de traitement.
**Acceptation** : upload et suivi inchangés fonctionnellement ; messages d'erreur clairs ; fichiers d'origine jamais modifiés.

## D3 — Résultats & exports
**Contenu**
- Barre de **filtres en chips** (thème, sentiment, signaux, statut revue, recherche).
- `Table` triable/paginée, densité réglable, en-tête collant ; badges sentiment/signaux.
- `Drawer` de détail verbatim (texte anonymisé, thèmes+scores, sentiment, signaux, confiance, colonnes d'origine).
- Exports CSV/XLSX en boutons ; états vides/chargement.
**Acceptation** : filtre < 2 s ; exports conformes POC inchangés ; correctif filtre Thème préservé.

## D4 — Revue humaine
**Contenu**
- **Mode focus** : une carte verbatim à la fois, sélecteurs niv.1/niv.2 **contraints par la taxonomie**, sentiment, signaux.
- Progression dans la file (n/total), **raccourcis clavier** (valider/corriger/suivant).
- Confirmation visuelle « corrigé » ; export des corrections.
**Acceptation** : impossible de choisir un couple invalide ; corrections tracées inchangées.

## D5 — Tableaux de bord & dataviz
**Contenu**
- Grille de `StatCard` (volume, % revue, erreurs, durée, taux de correction).
- **Charts** re-stylés sur tokens : distribution thèmes (`BarList`), sentiments, **thème × sentiment** (`StackedSentimentBar`), tendances (`Sparkline`/`Donut`).
- **KPI modèle** avec **alerte visuelle** sous seuils cibles.
- Layout en grille responsive desktop.
**Acceptation** : mêmes données qu'en V1 ; légendes lisibles ; alertes seuils visibles.

## D6 — Administration & comptes
**Contenu**
- **Utilisateurs** : `Table` + `Dialog` création/édition, badges rôle/état.
- **Administration** : `Tabs` (Configuration · Rétention · Audit) ; **purge** via `Dialog` de confirmation *danger* ; **audit** en table filtrable/paginée.
**Acceptation** : RBAC API inchangé ; purge toujours confirmée ; audit complet.

## D7 — Finition, accessibilité & recette UI
**Contenu**
- Passe **accessibilité** : contraste AA, focus visible partout, navigation clavier, `aria-*`.
- États vides/erreurs/chargement homogènes ; micro-interactions sobres (survols, transitions).
- Nettoyage : suppression des derniers `style={}` résiduels, page `/design` à jour.
- **Recette UI** (checklist visuelle) + vérif **non-régression** (build + `tsc` + recette V1 48/48).
- Documentation finale (capture des écrans clés dans la charte).
**Acceptation** : DoD V2 (§8 de la charte) entièrement cochée.

---

## Jalons
- **MV2-1** (fin D1) : nouvelle identité visible (shell + connexion + accueil).
- **MV2-2** (fin D3) : parcours cœur (lots → résultats) entièrement refondu — démontrable au métier.
- **MV2-3** (fin D7) : V2 complète, accessible, sans régression.

## Garde-fous V2
- Aucune nouvelle dépendance runtime ; offline strict préservé.
- Aucun changement d'API, de routes, de RBAC ni de garde-fous §10.
- La recette fonctionnelle V1 reste la référence de non-régression.
