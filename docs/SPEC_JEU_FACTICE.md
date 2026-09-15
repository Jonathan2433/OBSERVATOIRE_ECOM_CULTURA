# Cahier des charges du jeu de données factice

> **Objet.** Spécifier le jeu de données synthétique servant à la démonstration du 28 août 2026,
> et au-delà comme jeu de test technique durable de la chaîne.
>
> **Statut.** v1.0 — 12 août 2026. **Auteur.** Agent Product Owner (D-22).
> **Références.** `docs/CADRAGE_NOUVEAU_MODELE.md` (v1.2), `docs/PLAN_LOTS_NOUVEAU_MODELE.md`.
> **Générateur.** `scripts/generate_fake_dataset.py`.

---

## 1. Ce que ce jeu prouve, et ce qu'il ne prouve pas

**Objet de la démonstration du 28 août (D-21)** : l'application reste fonctionnelle après un
changement de moteur ML, incluant un nouveau référentiel, une nouvelle structure de fichiers
sources et l'ajout de fichiers.

| Ce jeu prouve | Ce jeu ne prouve **pas** |
|---|---|
| Que le nouveau référentiel charge, y compris avec des libellés de niveau 2 partagés entre plusieurs parents | Qu'un thème est correctement attribué à un verbatim réel |
| Que les 4 formats de fichiers sources sont lus, y compris avec des colonnes manquantes ou en défaut d'encodage | La qualité de la classification |
| Que le contrat de sortie produit **deux sentiments distincts** sur un verbatim à deux thèmes | Le taux d'erreur du modèle |
| Qu'aucun couple hors référentiel n'est produit | La calibration du score de confiance |
| Que le switch entre moteurs fonctionne | Le débit sur volume réel |
| Que la chaîne encaisse verbatims vides, très longs, PII, fautes, hors-sujet | La représentativité de quoi que ce soit |

> ⚠️ **Règle absolue de communication.** Aucune métrique produite sur ce jeu ne doit être
> présentée à Cultura comme une performance. Tout tableau de résultats issu de ce jeu porte en
> en-tête la mention **« données synthétiques — non représentatives de la production »**.
>
> **Rappel du précédent.** Le jeu de 7 000 verbatims du prototype était synthétique. Il a produit
> un F1-macro de 0,891 au niveau 2 qui a fait conclure que « le niveau 2 est excellent ». En
> réalité il ne contenait que 403 textes uniques dupliqués 17 fois, avec 99,6 % des lignes de
> test présentes à l'identique dans le train : le modèle récitait. Le défaut est resté invisible
> pendant deux mois. **Ce cahier des charges existe pour que cela ne se reproduise pas.**

---

## 2. Invariants — vérifiés automatiquement, bloquants

Le générateur échoue s'il ne peut pas les garantir. Un contrôle post-génération les revérifie.

| # | Invariant | Motif |
|---|---|---|
| **I-1** | **Zéro doublon de texte.** Chaque verbatim est unique dans l'ensemble du jeu. | Défaut n°1 du prototype (403 uniques pour 7 000 lignes). |
| **I-2** | **Split sans fuite par construction.** L'intersection des textes entre train, validation et test est vide. Le split est réalisé **avant** toute duplication éventuelle. | Défaut n°2 (99,6 % de fuite). |
| **I-3** | **Le sentiment n'est pas déductible de la note.** Au moins **25 %** des verbatims portent un sentiment discordant avec la tranche de note attendue. | Défaut n°3 : dans le prototype, note → sentiment était exact sur 7 000 lignes sans exception. Un modèle entraîné là-dessus n'apprend rien du texte. |
| **I-4** | **Tout couple (thème, sous-thème) appartient au référentiel.** | Garde-fou EF-5. |
| **I-5** | **Distribution déséquilibrée entre thèmes**, avec un rapport d'au moins 4 entre le thème le plus fréquent et le moins fréquent. | Le prototype était quasi parfaitement équilibré, ce qui n'arrive jamais en production et masque le comportement sur classes rares. |
| **I-6** | **Au moins 30 % des verbatims bi-thèmes portent des sentiments opposés** entre thème 1 et thème 2. | Le prototype en comptait **0 sur 28**. C'est le cas central de la demande métier (D-1). |
| **I-7** | **Tous les sous-thèmes du référentiel sont représentés** dans le train et dans le test. | La démonstration doit couvrir l'intégralité du référentiel (D-24). |
| **I-8** | **Chaque cas piège est référencé** dans un manifeste, avec le comportement attendu. | Sans manifeste, un cas piège est un bug non détecté. |

---

## 3. Volumétrie et distribution (D-24)

**Cible : ≈ 1 500 verbatims uniques.** Volume modeste assumé : l'objectif est la couverture et
le fonctionnement, pas l'apprentissage.

| Élément | Valeur |
|---|---|
| Verbatims uniques | **1 500** |
| Mono-thème | ≈ 1 200 (80 %) |
| Bi-thèmes | ≈ 300 (20 %) |
| dont **sentiments opposés** | ≈ 120 (40 % des bi-thèmes, soit 8 % du jeu) |
| Cas pièges | ≈ 80, répartis dans les trois splits |
| Split | 70 / 15 / 15 par **texte unique** |
| Couverture | 100 % des sous-thèmes, minimum 8 exemples chacun dans le train |

**Distribution entre thèmes.** Loi de puissance plutôt qu'uniforme, calibrée sur ce qu'on
observe en e-commerce : livraison, paiement et disponibilité dominent ; personnalisation, carte
cadeau et catalogue sont marginaux. Rapport imposé entre le thème le plus et le moins
représenté : **au moins 4** (I-5).

**Distribution des sentiments.** Environ 55 % négatif, 25 % neutre, 20 % positif — les
dispositifs de recueil d'irritants attirent les mécontents. Le prototype était à 34/33/33, ce
qui est un artefact.

**Notes de satisfaction.** Cohérentes en tendance avec le sentiment, **mais discordantes dans
25 % des cas** (I-3) : client agacé qui note 7 par habitude, client satisfait qui note bas pour
un détail, verbatim positif après une note basse donnée à chaud.

---

## 4. Le cas central — bi-thèmes à sentiments opposés

C'est le cas fondateur de la demande métier, et il n'existe dans aucune donnée disponible.
Modèle de référence, formulé par le métier :

> *« le paiement n'aboutit pas, mais j'ai facilement trouvé mon produit sur le site »*
> → thème 1 = Paiement, **Négatif** · thème 2 = Recherche produit, **Positif**

**Règles de construction** des ≈ 120 cas :

1. Deux thèmes **de parents différents**, pour tester la contrainte hiérarchique.
2. Sentiments strictement opposés (Négatif / Positif), jamais Neutre des deux côtés.
3. Connecteur adversatif explicite dans au moins 70 % des cas (« mais », « en revanche »,
   « par contre », « cela dit ») — et **absent dans les 30 % restants**, pour vérifier que le
   modèle ne se repose pas sur un mot-clé.
4. Ordre des polarités alterné : la moitié commence par le négatif, l'autre par le positif.
5. **Note de satisfaction intermédiaire** (4 à 7) : une note unique ne peut pas justifier deux
   sentiments opposés. C'est précisément ce qui force le modèle à lire le texte.
6. Au moins 20 cas placent les deux thèmes sur une **frontière poreuse** connue.

---

## 5. Cas pièges (D-25)

≈ 80 cas, chacun inscrit au manifeste `fake_dataset_traps.json` avec son comportement attendu.

| Catégorie | Cas | Comportement attendu |
|---|---|---|
| **Texte vide ou dégénéré** | chaîne vide · espaces seuls · `"..."` · un seul caractère | `nb_themes = 0`, revue humaine, aucune exception |
| **Longueur extrême** | 1 à 3 mots · 900+ caractères · au-delà de la troncature à 512 tokens | Traité sans erreur ; la troncature ne casse pas la sortie |
| **Casse et ponctuation** | tout en majuscules · sans aucune ponctuation · ponctuation excessive | Traité ; permet de mesurer l'effet de `lowercase` |
| **Fautes et langage** | fautes d'orthographe · abréviations SMS · phonétique · anglicismes | Classé sans dégradation catastrophique |
| **Emojis et Unicode** | emojis seuls · emojis mêlés · caractères combinants · NBSP | Nettoyage effectif, pas d'exception |
| **PII** | adresses e-mail · téléphones aux formats FR · **numéros de commande au format `P########`** · noms propres · noms de marque à ne pas masquer | Masquage effectif ; **le format `P########` n'a jamais été rencontré par le regex actuel** |
| **Hors sujet** | texte sans rapport · suite de chiffres · copier-coller d'URL · spam | Confiance basse et revue humaine ; le repli produit un thème par argmax, ce qui est un comportement à observer et documenter |
| **Homonymie de sous-thèmes** | verbatims dont le sous-thème existe sous **deux parents différents** | **Cas critique (B2)** : le couple retourné doit rester cohérent avec le parent retenu |
| **Frontières poreuses** | retard sur un retrait en magasin · rupture constatée au retrait · annulation pour rupture | Documente le comportement sur les cas ambigus ; sert de base à l'atelier de règles d'arbitrage |
| **Trois sujets ou plus** | verbatims mentionnant 3 sujets distincts | Le plafond de 2 s'applique ; vérifie qu'aucune information ne casse la sortie |
| **Défauts de fichier** | colonne absente · en-tête renommé · cellule numérique là où du texte est attendu · `Pas du tout satisfait€` (défaut d'encodage observé) · ligne entièrement vide | **Le chargeur échoue explicitement** sur colonne attendue manquante (R-18), et ne dégrade jamais en silence |

---

## 6. Artefacts produits

Deux familles, cohérentes entre elles : les mêmes verbatims, vus sous deux angles.

### 6.1 Le jeu labellisé — entraînement et évaluation

`data/raw/fake/fake_labeled.xlsx`

| Colonne | Contenu |
|---|---|
| `verbatim_id` | identifiant stable, permet de relier aux fichiers d'entrée |
| `source` | MDTC-postachat · MDTC-postrecep · Mopinion-desktop · Mopinion-mobile |
| `date` | – |
| `verbatim_original` | le texte |
| `satisfaction_raw` | valeur brute dans l'échelle de la source |
| `satisfaction_norm` | valeur normalisée selon D-20, table de conversion documentée |
| `nb_themes` | 1 ou 2 |
| `theme1_niv1` · `theme1_niv2` · **`theme1_sentiment`** | – |
| `theme2_niv1` · `theme2_niv2` · **`theme2_sentiment`** | **sentiment propre, pas une recopie** (D-1) |
| `signal_*` | selon la redéfinition du lot L4 ; à défaut, les trois signaux actuels |
| `split` | train / val / test, attribué par texte unique (I-2) |
| `trap_id` | référence au manifeste si le verbatim est un cas piège, vide sinon |

### 6.2 Les fichiers d'entrée — démonstration de l'ingestion

Quatre fichiers Excel reproduisant **exactement** les colonnes des maquettes reçues le 12 août.
C'est ce qui démontre le « changement de structure des fichiers et ajout de fichier » (D-21).

| Fichier | Colonnes | Champs libres |
|---|---|---|
| `fake_MDTC-postachat-web.xlsx` | 9 | `Justification du niveau de satisfaction`, `Produits non trouvé`, `Suggestions d'amélioration` |
| `fake_MDTC-postrecep-web.xlsx` | 7 | `Justification du niveau de satisfaction` |
| `fake_mopinion_desktop.xlsx` | 25 | `Merci ! Avez-vous tout de même une remarque…`, `Décrivez nous votre problème` |
| `fake_mopinion_mobilev2.xlsx` | 25 | `Avez-vous une remarque ou des idées…`, `Ce n'est pas cela ? Décrivez-nous le problème.`, `Décrivez-nous le problème.`, `Dites-nous en plus sur votre problème.` |

**Application de D-17** — un verbatim par champ libre rempli : un même répondant peut produire
1 à 3 verbatims sur MDTC post-achat, 1 à 4 sur Mopinion mobile. Le générateur produit donc
**moins de lignes de fichier que de verbatims**, et la colonne `verbatim_id` permet de
reconstituer le lien. C'est cette mécanique qu'il faut démontrer : elle est nouvelle.

Les colonnes écartées par D-18 (rejeu de session, captures d'écran, HTML, agent utilisateur,
e-mail) sont **présentes dans les fichiers** — pour que la démonstration soit réaliste — mais
le chargeur ne doit pas les ingérer. Le contrôle qu'elles n'atteignent pas la base fait partie
de la recette.

### 6.3 Le manifeste des cas pièges

`data/raw/fake/fake_dataset_traps.json` : un objet par cas piège, avec `trap_id`, `categorie`,
`description`, `comportement_attendu`, `verbatim_id`. Il constitue le scénario de test de la
démonstration, et reste utilisable en septembre sur les vraies données.

### 6.4 Le rapport de contrôle

`data/raw/fake/fake_dataset_report.json` : vérification automatique des 8 invariants, plus les
statistiques de distribution. **La génération est réputée échouée si un seul invariant n'est pas
satisfait.**

---

## 7. Conception du texte

Le piège du prototype était un français trop propre : 29 à 90 caractères, aucune faute, aucun
registre familier, aucune PII sur 7 000 verbatims de e-commerce.

**Règles retenues :**

- **Longueurs** : distribution étalée de 3 à 400 caractères, médiane visée autour de 90, avec
  une queue longue assumée. Pas de plage étroite.
- **Registres** : mélange de formulations soignées, familières, télégraphiques et énervées.
- **Bruit** : environ 20 % des verbatims comportent au moins une faute, une abréviation ou une
  ponctuation irrégulière.
- **Unicité** : construction combinatoire à partir de patrons par sous-thème, croisés avec des
  banques de tournures, d'intensifieurs et de compléments contextuels. Toute collision est
  détectée et régénérée (I-1).
- **Pas de marqueur exploitable** : aucun mot ne doit permettre d'identifier un sous-thème de
  façon déterministe, sans quoi le modèle apprend un dictionnaire et non du langage. Contrôle :
  aucun terme ne doit être présent dans plus de 80 % des verbatims d'un sous-thème et dans
  moins de 5 % des autres.

---

## 8. Dépendances et séquencement

| Étape | Dépendance | Statut au 12/08 |
|---|---|---|
| Rédaction du cahier des charges | aucune | **fait** |
| Développement du générateur | aucune — paramétré par le référentiel | **réalisable immédiatement** |
| Test du générateur | référentiel actuel (20/67), en attendant | **réalisable immédiatement** |
| **Génération du jeu définitif** | **référentiel Cultura** (Q-2, sollicitation B1, annoncé pour le 12/08) | **bloqué** |
| Patrons de phrases par sous-thème | référentiel Cultura — les libellés changent | **bloqué** |

> Le générateur est conçu **générique et surchargeable** : les patrons sont dérivés
> automatiquement des libellés du référentiel, et peuvent être remplacés sous-thème par
> sous-thème via un fichier de surcharge. Dès réception du référentiel Cultura, la génération
> tourne sans réécriture.

---

## 9. Ce que ce jeu ne dispense pas de faire

- **Annoter les vraies données** (D-23, début septembre). Aucune donnée synthétique ne remplace
  un corpus réel annoté. Le trimestre annoncé arrivera **non annoté** : il n'existe plus aucune
  source d'étiquettes depuis les réponses A3 et A5 de Cultura.
- **Établir une baseline honnête** sur données réelles. Les chiffres d'août n'en sont pas une.
- **Mesurer le débit** sur volume réel. 1 500 verbatims ne disent rien de 11 000.
- **Calibrer la confiance.** Reporté hors du 28 août.

---

*Projet interne Cultura / eXalt — usage confidentiel.*
