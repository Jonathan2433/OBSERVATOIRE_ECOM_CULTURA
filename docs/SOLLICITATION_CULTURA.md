# Sollicitation groupée Cultura — Refonte du moteur de classification

> **Objet.** Liste unique et priorisée des informations et décisions attendues de Cultura pour
> la refonte du moteur ML. Groupée volontairement en **une seule sollicitation** pour limiter
> les allers-retours en période de congés.
>
> **Émetteur.** eXalt — Jonathan Dupau. **Date.** 12 août 2026.
> **Réponse attendue.** Bloc A sous 48 h · blocs B et C sous 5 jours ouvrés · blocs D et E avant
> le 21 août.
> **Références.** `docs/CADRAGE_NOUVEAU_MODELE.md`, `docs/PLAN_LOTS_NOUVEAU_MODELE.md`.

---

## Comment lire ce document

Chaque question comporte :

- **La question**, formulée pour être posée telle quelle à Cultura.
- **Pourquoi on la pose** — l'enjeu, en langage métier.
- **Sans réponse** — ce qui se passe concrètement si elle reste ouverte.

Les questions marquées 🔴 sont **bloquantes** : le projet ne peut pas avancer sans elles.

---

## Bloc A — Les données 🔴

> **Contexte à donner à Cultura.** Nous avons reçu 4 fichiers de structure (MDTC post-achat web,
> MDTC post-réception web, Mopinion desktop, Mopinion mobile V2) contenant les colonnes et
> quelques exemples de valeurs. Ils sont très utiles pour spécifier la reprise, mais ils ne
> contiennent que 11 à 16 lignes fictives : **aucune mesure n'est possible dessus**, et aucun
> modèle ne peut être entraîné avec.

### A1 🔴 — Quand recevons-nous les exports réels, et que contiennent-ils ?

**La question.** À quelle date pouvons-nous disposer d'un export réel de production ? Sur quelle
période, pour quel volume de réponses, et pour lesquels des formulaires ?

**Pourquoi on la pose.** Tout le projet en dépend. Nous ne pouvons ni mesurer la qualité
actuelle, ni entraîner, ni fixer d'objectif chiffré sur des fichiers de structure. Le premier
lot du plan — l'audit des données — est un **jalon de décision** : c'est lui qui dira si les
nouveaux comportements demandés sont réalisables dans le calendrier.

**Sans réponse.** L'échéance du 30 août n'est pas tenable. Le chemin critique du projet est de
21 jours ouvrés ; chaque jour d'attente est perdu sans rattrapage possible.

### A2 — Combien de formulaires existe-t-il au total, et leurs structures sont-elles stables ?

**La question.** Les 4 fichiers reçus sont tous suffixés *web*, *desktop* ou *mobile V2* :
existe-t-il des variantes application mobile pour MDTC, ou d'autres formulaires que nous
n'avons pas vus ? Les colonnes évoluent-elles au fil des campagnes ? Qui nous prévient d'un
changement ?

**Pourquoi on la pose.** Chaque formulaire a un schéma différent et demande son propre module de
lecture. Nous en avons budgété 4. Un cinquième découvert en cours de route décale le
calendrier. Et si les formulaires évoluent sans préavis, la chaîne se casse silencieusement en
production.

**Sans réponse.** Nous développons pour 4 formulaires et considérons tout autre format comme
hors périmètre.

### A3 🔴 — Quelle correspondance entre les sujets cochés par le client et le référentiel de thèmes ?

**La question.** Dans les formulaires Mopinion, le client sélectionne lui-même un sujet avant
d'écrire (« Je rencontre un problème lors du paiement par carte cadeau », « Sur quel sujet
porte votre question ? », « Dites-nous en plus : »). Pouvez-vous nous fournir **la liste
complète des choix possibles pour chacune de ces questions**, et nous indiquer à quel thème du
référentiel chacun correspond ? Et selon votre expérience, ces réponses sont-elles fiables — un
client qui coche « problème de paiement » parle-t-il effectivement de paiement ?

**Pourquoi on la pose.** C'est la question la plus rentable du projet. Ces sujets cochés vont
nous servir **d'étiquettes de départ** pour entraîner le modèle : chaque réponse Mopinion
devient un exemple d'apprentissage sans qu'aucune annotation manuelle soit nécessaire. Cela
supprime plusieurs semaines de travail. Mais si la correspondance avec le référentiel est
incomplète, ou si les clients se trompent souvent de case, nous entraînerions le modèle sur des
erreurs — à grande échelle.

**Sans réponse.** Nous devons faire annoter manuellement plusieurs milliers de verbatims, ce qui
ne tient pas dans le calendrier.

### A4 — Le champ `tags` : quelle est cette nomenclature ?

**La question.** Le champ `tags` des exports Mopinion contient des valeurs numérotées du type
« 3- Connexion_création de compte ». S'agit-il d'une nomenclature Cultura déjà en production ?
Qui la maintient, à quoi sert-elle, et quelle est sa relation avec le référentiel de thèmes que
nous utilisons ? Est-elle appliquée automatiquement ou saisie par une équipe ?

**Pourquoi on la pose.** Si Cultura dispose déjà d'une classification opérationnelle, il faut
savoir laquelle fait foi avant d'entraîner quoi que ce soit. Livrer un modèle qui produit une
nomenclature concurrente de celle déjà utilisée en interne serait un échec, même avec de bonnes
métriques.

**Sans réponse.** Nous ignorons ce champ, au risque de dupliquer un travail existant.

### A5 🔴 — Comment obtenir des étiquettes sur les réponses MDTC ?

**La question.** Contrairement à Mopinion, les formulaires MDTC ne proposent aucun choix de sujet
au client : il n'y a que du texte libre. Disposez-vous d'un historique de réponses MDTC déjà
classées, ou d'une équipe capable d'en classer quelques centaines ?

**Pourquoi on la pose.** Nous obtenons gratuitement des étiquettes sur Mopinion (question A3),
mais rien sur MDTC. Un modèle entraîné surtout sur Mopinion puis appliqué à MDTC peut se
dégrader fortement sans qu'on s'en aperçoive : les deux sources n'ont ni le même contexte, ni le
même style d'écriture, ni les mêmes sujets. Nous avons besoin d'au moins un échantillon MDTC
classé pour **vérifier** le modèle, même si nous ne l'entraînons pas dessus.

**Sans réponse.** La qualité du modèle sur MDTC ne sera pas démontrable, et nous devrons le
signaler comme une réserve à la mise en production.

### A6 — Comment convertir les échelles de satisfaction entre les sources ?

**La question.** MDTC utilise un libellé à 4 modalités (« Pas du tout satisfait », « Plutôt pas
satisfait(e) », « Plutôt satisfait(e) »…) **et** un score de recommandation de 0 à 10. Mopinion
utilise une échelle de 1 à 5. Existe-t-il chez Cultura une table de conversion officielle entre
ces échelles ? Laquelle est la référence dans vos analyses ?

**Pourquoi on la pose.** Nous avons retenu le niveau de satisfaction plutôt que le score de
recommandation, parce qu'il porte sur l'expérience vécue et non sur l'intention de recommander
la marque. Pour comparer des volumes entre sources, il faut une conversion écrite et validée par
vous — sinon chaque source raconte une histoire différente.

**Sans réponse.** Nous proposons une conversion et la documentons comme hypothèse eXalt, à
valider ultérieurement.

### A7 — Un défaut d'encodage à confirmer

**La question.** Le fichier MDTC contient la valeur `Pas du tout satisfait€`, où le caractère
final semble être une erreur d'encodage. Ce défaut est-il présent dans vos exports réels ou
seulement dans le fichier de structure ?

**Pourquoi on la pose.** Un caractère parasite dans une modalité de réponse casse silencieusement
la lecture du fichier et fausse tous les comptages sur cette modalité.

**Sans réponse.** Nous traitons ce cas de manière défensive dans le module de lecture.

---

## Bloc B — Le référentiel de thèmes 🔴

### B1 🔴 — Nous transmettre le référentiel qui fait foi

**La question.** Merci de nous transmettre le fichier du référentiel de thèmes et sous-thèmes
dans sa version en vigueur. A-t-il évolué depuis les 20 thèmes et 67 sous-thèmes du prototype ?

**Pourquoi on la pose.** Le référentiel détermine l'espace de réponse du modèle. Nous ne pouvons
pas préparer les données ni entraîner sans lui.

**Sans réponse.** Nous travaillons sur le référentiel du prototype, avec le risque de devoir tout
reprendre si le vôtre diffère.

### B2 🔴 — Un même libellé de sous-thème apparaît-il sous deux thèmes différents ?

**La question.** Dans votre référentiel, un sous-thème comme « Délai trop long » peut-il exister
à la fois sous « Livraison » et sous « Service client » ?

**Pourquoi on la pose.** Contrainte technique bloquante : l'application refuse actuellement de
démarrer si un même libellé de sous-thème apparaît sous deux thèmes parents. Si c'est le cas
dans votre référentiel, il faut modifier le cœur du système de codage — environ 4 jours de
développement non prévus, qui remettraient en cause l'échéance.

**Sans réponse.** Nous le découvrirons au chargement du fichier, dans le pire des cas au milieu
du projet.

### B3 — Les libellés de sous-thèmes peuvent-ils devenir neutres ?

**La question.** Vos sous-thèmes sont formulés négativement (« Recherche peu efficace », « Délai
non respecté »). Accepteriez-vous de les reformuler en sujets neutres (« Recherche produit »,
« Délai de livraison »), la satisfaction ou l'insatisfaction étant portée séparément par le
sentiment ?

**Pourquoi on la pose.** Le modèle doit désormais attribuer un sentiment propre à chaque thème.
Avec des libellés négatifs, un retour élogieux devient inexprimable : dans le jeu actuel, un
verbatim disant « recommandations pertinentes » a dû être étiqueté « Recommandations non
pertinentes » avec un sentiment positif — une contradiction que le modèle ne peut pas
apprendre. Un seul sous-thème positif existe aujourd'hui, et c'est de très loin le plus mal
classé de tout le référentiel.

**Sans réponse.** Les retours positifs resteront mal traités, ce qui prive Cultura de
l'information « ce qui fonctionne, ne pas y toucher » au moment d'arbitrer les refontes.

### B4 — Comment trancher entre deux thèmes voisins ?

**La question.** Quand un client se plaint d'un retard sur une commande retirée en magasin,
faut-il classer en « Suivi de commande et livraison » ou en « Click & Collect » ? Existe-t-il des
règles écrites pour ces cas limites ? Pouvons-nous organiser une demi-journée d'atelier pour les
formaliser ?

**Pourquoi on la pose.** C'est le principal plafond de performance mesuré. Aujourd'hui, « Click
& Collect » est absorbé par « Suivi de commande » dans 45 cas sur 62 — et ce, sur des textes que
le modèle avait déjà vus à l'entraînement. Ce n'est pas un problème de puissance du modèle mais
de frontières entre thèmes : sans règles écrites, deux personnes classent différemment le même
verbatim, et le modèle apprend cette incohérence.

**Sans réponse.** Nous documentons ce plafond comme structurel et non corrigeable par le modèle.
Concrètement, cela signifie que les volumes par thème resteront partiellement faussés — donc les
arbitrages d'investissement qu'ils servent à éclairer aussi.

---

## Bloc C — Les attentes métier

### C1 — Que déclenche concrètement chacun des trois signaux ?

**La question.** Le modèle produit trois alertes : rupture client, risque d'attrition,
insatisfaction forte. Pour chacune : qui la reçoit, quelle action est déclenchée, dans quel
délai ? Deux d'entre elles déclenchent-elles la même chose ?

**Pourquoi on la pose.** Nos mesures montrent que « risque d'attrition » et « insatisfaction
forte » sont en pratique le même signal : ils s'activent sur les mêmes verbatims, à deux
exceptions près sur 7 000. Si les deux déclenchent la même action, nous n'en produisons qu'un —
un modèle en moins à entraîner et à exécuter, donc du temps de traitement gagné. Par ailleurs,
« rupture client » ne représente que 0,4 % des cas, ce qui est trop peu pour garantir sa
fiabilité.

**Sans réponse.** Nous reconduisons les trois signaux à l'identique, sans pouvoir nous engager
sur la fiabilité de « rupture client ».

### C2 — Quel niveau de relecture humaine acceptez-vous ?

**La question.** Sur environ 11 000 réponses par mois, combien votre équipe peut-elle en relire ?
Nous proposons de viser 10 à 15 %, soit 1 100 à 1 650 verbatims mensuels.

**Pourquoi on la pose.** Le modèle signale les cas dont il n'est pas sûr, pour relecture. Ce
curseur est aujourd'hui inutilisable : à un réglage il envoie 10 % en relecture, au réglage
immédiatement supérieur il en envoie 100 %. Le rendre pilotable est un chantier à part entière,
que nous ne lancerons que si vous confirmez en avoir l'usage.

**Sans réponse.** Nous conservons le réglage actuel et signalons que le taux de relecture n'est
pas garanti.

### C3 — Validation des objectifs chiffrés

**La question.** Nous vous proposerons des objectifs de qualité mesurables une fois les données
réelles reçues. Qui les valide côté Cultura, et sous quel délai ?

**Pourquoi on la pose.** L'objectif du cahier des charges initial n'est pas mesurable en l'état :
les chiffres de performance publiés sur le prototype sont invalides, parce que le modèle avait
été évalué sur des textes qu'il avait déjà vus à l'entraînement. Nous devons repartir d'une
mesure honnête avant de nous engager sur une cible.

**Sans réponse.** Nous proposons des objectifs argumentés et les documentons comme provisoires.

---

## Bloc D — Protection des données

### D1 — Confirmation du périmètre de données traitées

**La question.** Vos exports Mopinion contiennent des liens de rejeu de session Contentsquare,
des captures d'écran hébergées, le code HTML de la page consultée, l'agent utilisateur et une
colonne destinée à l'adresse e-mail. Nous prévoyons de **ne pas les intégrer** : nous ne
conserverions que le type de page, l'URL et le type d'appareil, qui nous servent à localiser
l'irritant. Confirmez-vous ?

**Pourquoi on la pose.** Le cahier des charges pose que seul le verbatim anonymisé est conservé
en base. Un lien de rejeu de session permet de revoir la navigation d'un client identifiable :
l'intégrer élargirait significativement le périmètre de données personnelles de l'application,
avec une durée de conservation de 13 mois, et sans aucun apport pour la classification.

**Sans réponse.** Nous appliquons le périmètre restreint par défaut et le rendons configurable.

### D2 — La colonne e-mail est-elle renseignée en production ?

**La question.** La colonne « Pour identifier les problèmes, votre adresse e-mail peut… » est
vide dans le fichier de structure. Est-elle renseignée dans vos exports réels ?

**Pourquoi on la pose.** Si oui, elle doit être écartée dès la lecture du fichier, avant tout
stockage. Le prototype n'avait jamais rencontré d'adresse e-mail dans les données — le
mécanisme d'anonymisation n'a donc jamais été éprouvé sur des cas réels.

**Sans réponse.** Nous écartons la colonne systématiquement.

---

## Bloc E — Organisation et calendrier

### E1 — Qui valide le nouveau modèle avant mise en service ?

**La question.** Quelle personne, ou quelle instance, prononce l'accord de mise en service ? Sur
quelle base : un échantillon relu, une réunion de présentation, un document signé ?

**Pourquoi on la pose.** Les tests automatisés existants vérifient que l'application fonctionne,
pas que le modèle classe correctement. Un accord humain nommé est nécessaire.

**Sans réponse.** La mise en service n'a pas de responsable identifié.

### E2 — Quelle est la date effective de mise en service ?

**La question.** Le 30 août 2026 est un dimanche. Le dernier jour ouvré est le vendredi 28 août.
Quelle date retenez-vous, et qui la prononce ?

**Pourquoi on la pose.** Deux jours de différence sur un calendrier sans marge.

### E3 — Vos disponibilités en août

**La question.** Qui est joignable côté Cultura entre le 12 et le 28 août, pour l'atelier de la
question B4 et pour la relecture de validation ?

**Pourquoi on la pose.** Deux étapes du projet dépendent de votre disponibilité en pleine période
de congés.

### E4 🔴 — Un scénario de repli, à valider maintenant plutôt que fin août

**La question.** Si le calendrier se tend, acceptez-vous de recevoir le 28 août un modèle
**entraîné, mesuré et comparé à l'actuel**, présenté et démontré, la mise en service effective
étant décalée à la première semaine de septembre ?

**Pourquoi on la pose.** eXalt doit être transparent : l'ensemble du périmètre demandé représente
plus de temps de travail que le calendrier n'en offre, et les fichiers réels ne sont pas encore
arrivés. Nous préférons poser cette option maintenant, à froid, plutôt que de la découvrir dans
l'urgence le 27 août. Ce repli ne fait perdre aucun travail : il décale uniquement la bascule en
production.

**Sans réponse.** Nous maintenons l'objectif du 28 août et vous alertons au plus tard le
21 août si le jalon n'est pas tenu.

### E5 — Un interlocuteur unique

**La question.** Pouvons-nous convenir d'un interlocuteur unique pour ce sujet, et d'un délai de
réponse cible ?

**Pourquoi on la pose.** Le projet comporte trois points de non-retour datés. Un délai de réponse
non maîtrisé les fait tomber mécaniquement.

---

## Récapitulatif — les 6 questions bloquantes

| # | Question | Attendu |
|---|---|---|
| **A1** | Date et contenu des exports réels | **48 h** |
| **A3** | Correspondance sujets cochés ↔ référentiel, et leur fiabilité | **48 h** |
| **A5** | Comment obtenir des étiquettes sur MDTC | 5 j |
| **B1** | Le fichier du référentiel en vigueur | **48 h** |
| **B2** | Un libellé de sous-thème peut-il exister sous deux thèmes ? | **48 h** |
| **E4** | Acceptation du scénario de repli | 5 j |

---

*Projet interne Cultura / eXalt — usage confidentiel.*
