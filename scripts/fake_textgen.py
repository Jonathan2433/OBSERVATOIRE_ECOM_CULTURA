# -*- coding: utf-8 -*-
"""Moteur de composition de verbatims synthétiques français.

Conforme à ``docs/SPEC_JEU_FACTICE.md`` §7 :
  - longueurs étalées, registres variés, bruit assumé ;
  - unicité garantie par construction combinatoire ;
  - aucun marqueur lexical déterministe d'un sous-thème.

Les patrons de phrase sont **dérivés automatiquement des libellés du référentiel**,
ce qui rend le module indépendant de la taxonomie employée : il fonctionnera tel
quel avec le nouveau référentiel Cultura. Une surcharge par sous-thème reste
possible via ``patrons_surcharge`` (cf. SPEC §8).

ARTEFACT DE TEST — ne fait partie ni de la chaîne d'entraînement, ni de la
chaîne de production.
"""
from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------- #
#  Banques lexicales
# --------------------------------------------------------------------------- #
OUV_NEG = ["", "", "", "franchement ", "honnetement ", "sincerement ", "je suis decu, ",
           "c'est la 2e fois, ", "vraiment ", "encore une fois ", "je ne comprends pas, ",
           "petit souci : ", "gros probleme : ", "attention ", "bonjour, ", "alors la ",
           "j'hallucine, ", "c'est penible, ", "aucune excuse : ", "deja la semaine derniere, "]
OUV_POS = ["", "", "", "super, ", "top ! ", "rien a dire, ", "un vrai plaisir, ", "bravo, ",
           "je suis ravi, ", "parfait, ", "merci beaucoup, ", "tres content, ", "au top, ",
           "excellent, ", "comme d'habitude, ", "franchement bien, "]
OUV_NEU = ["", "", "", "", "juste une remarque : ", "pour info, ", "a signaler : ", "ceci dit, ",
           "simple retour : ", "sans plus, ", "bof, ", "ni bien ni mal, ", "a voir, "]

CLO_NEG = ["", "", "", " c'est inadmissible.", " tres decevant.", " a corriger svp.",
           " je ne recommande pas.", " merci d'y remedier.", " ca gache tout.",
           " j'attends toujours.", " personne ne repond.", " je vais aller ailleurs.",
           " c'est vraiment dommage.", " a revoir completement.", " lamentable."]
CLO_POS = ["", "", "", " je recommande.", " continuez comme ca !", " rien a redire.",
           " tres satisfait.", " je reviendrai.", " un sans faute.", " merci !",
           " c'est appreciable.", " parfait pour moi.", " bonne experience."]
CLO_NEU = ["", "", "", "", " a ameliorer peut-etre.", " sans plus.", " voila.", " c'est tout.",
           " je signale simplement.", " pour votre information."]

INT_FORT = ["vraiment ", "completement ", "totalement ", "carrement ", "franchement ",
            "hyper ", "extremement ", "particulierement "]
INT_FAIBLE = ["un peu ", "plutot ", "assez ", "legerement ", "relativement ", "moyennement "]

CTX = ["", "", "", " sur le site", " sur l'appli", " depuis mon telephone", " en magasin",
       " lors de ma derniere commande", " ce matin", " hier soir", " depuis 3 jours",
       " apres la mise a jour", " avec mon compte", " au moment de valider",
       " pendant les soldes", " sur la page produit", " a la caisse", " en click and collect",
       " la semaine derniere", " ce week-end", " sur chrome", " depuis la refonte"]

ADJ_NEG = ["penible", "inacceptable", "decevant", "complique", "lent", "confus", "opaque",
           "frustrant", "incomprehensible", "aberrant", "flou", "mal fichu"]
ADJ_POS = ["simple", "rapide", "clair", "efficace", "pratique", "fluide", "intuitif",
           "impeccable", "agreable", "bien fait", "reactif", "au point"]

# §4 règle 3 : connecteur adversatif présent dans ~70 % des cas divergents seulement.
ADVERS = [" mais ", " en revanche ", " par contre ", " cela dit ", " ceci dit ",
          " neanmoins ", " toutefois "]
NEUTRE_LIEN = [". ", ". ", ". et ", ", et ", ". aussi ", ". autre chose : ", ". sinon ", ". "]

QUEUE_LONGUE = [
    "j'ai deja contacte le service client sans succes",
    "je precise que je suis client depuis plusieurs annees",
    "j'ai essaye sur deux navigateurs differents et c'est pareil",
    "j'ai refait la manipulation trois fois",
    "je joins une capture si besoin",
    "merci de me tenir informe par retour",
    "ce n'est pas la premiere fois que cela arrive",
    "j'espere une reponse rapide de votre part",
]
TRES_COURT = ["nul.", "bof", "top", "rien", "ok", "??", "parfait", "a revoir", "mouais", "!!"]

FAUTES = {"vraiment": "vraimen", "impossible": "imposible", "commande": "comande",
          "livraison": "livrason", "toujours": "tjrs", "beaucoup": "bcp",
          "probleme": "problme", "site": "cite", "c'est": "cest",
          "s'il vous plait": "svp", "tres": "tre", "paiement": "payement",
          "magasin": "magazin", "rien": "rein"}

# --------------------------------------------------------------------------- #
#  Accentuation — remplacement borné au mot entier
# --------------------------------------------------------------------------- #
ACCENTS = {
    "penible": "pénible", "decu": "déçu", "decevant": "décevant", "tres": "très",
    "apres": "après", "probleme": "problème", "reponse": "réponse", "repond": "répond",
    "reactif": "réactif", "complique": "compliqué", "numero": "numéro",
    "telephone": "téléphone", "deja": "déjà", "derniere": "dernière", "premiere": "première",
    "reserve": "réservé", "recu": "reçu", "annule": "annulé", "annonce": "annoncé",
    "creation": "création", "fidelite": "fidélité", "numerique": "numérique",
    "delai": "délai", "delais": "délais", "cote": "côté", "passe": "passé",
    "trouve": "trouvé", "gere": "géré", "gerer": "gérer", "etait": "était", "ete": "été",
    "etre": "être", "completement": "complètement", "sincerement": "sincèrement",
    "honnetement": "honnêtement", "remedier": "remédier", "espere": "espère",
    "incomprehensible": "incompréhensible", "agreable": "agréable", "interet": "intérêt",
    "acces": "accès", "verifier": "vérifier", "essaye": "essayé", "contacte": "contacté",
    "informe": "informé", "succes": "succès", "annees": "années", "differents": "différents",
    "meme": "même", "achete": "acheté", "livre": "livré", "disponibilite": "disponibilité",
    "securite": "sécurité", "operation": "opération", "reference": "référence",
    "categorie": "catégorie", "qualite": "qualité", "desole": "désolé", "echange": "échange",
    "echec": "échec", "etape": "étape", "etapes": "étapes", "precise": "précise",
    "respecte": "respecté", "ameliorer": "améliorer", "appreciable": "appréciable",
    "experience": "expérience", "legerement": "légèrement", "extremement": "extrêmement",
    "particulierement": "particulièrement", "carrement": "carrément", "plutot": "plutôt",
    "voila": "voilà", "gache": "gâche", "depend": "dépend", "peut-etre": "peut-être",
    "reactive": "réactive", "decevante": "décevante", "compliquee": "compliquée",
    "revue": "revue", "elevee": "élevée", "creditees": "créditées",
}
_ACC_RE = re.compile(r"\b(" + "|".join(sorted(ACCENTS, key=len, reverse=True)) + r")\b")


def _accentuer(texte: str) -> str:
    """Réintroduit les accents français, mot entier uniquement.

    Un remplacement de sous-chaîne transformait « completement » en
    « complétément » : d'où la borne ``\\b``.
    """
    texte = _ACC_RE.sub(lambda m: ACCENTS[m.group(0)], texte)
    texte = re.sub(r"\bca (ne|gache|bloque|depend|va)\b", lambda m: "ça " + m.group(1), texte)
    texte = re.sub(r"\balors la\b", "alors là", texte)
    texte = re.sub(r"\bcomme ca\b", "comme ça", texte)
    return texte


# --------------------------------------------------------------------------- #
#  Bruit (≈ 20 % des verbatims, cf. SPEC §7)
# --------------------------------------------------------------------------- #
def _bruiter(texte: str, rng) -> str:
    mode = rng.random()
    if mode < 0.45:
        for faux, vrai in FAUTES.items():
            if faux in texte and rng.random() < 0.5:
                return texte.replace(faux, vrai, 1)
        return texte
    if mode < 0.62:
        return texte.upper()
    if mode < 0.78:
        return re.sub(r"[.,!?]", "", texte)
    if mode < 0.92:
        return texte.replace(".", rng.choice(["!!!", "...", " !!", " ??"]), 1)
    return texte.replace(" ", "  ", 1) + rng.choice(["  ", " ...", "!!!"])


# --------------------------------------------------------------------------- #
#  Dérivation des patrons depuis les libellés du référentiel
# --------------------------------------------------------------------------- #
_STOP = {"de", "du", "des", "la", "le", "les", "un", "une", "en", "et", "a", "au", "aux",
         "par", "pour", "sur", "non", "pas", "trop", "peu", "mal", "ou", "d", "l", "vs",
         "dans", "avec", "son", "sa", "est", "plus", "moins", "tout", "sans",
         "que", "qui", "quoi", "ne", "nos", "vos", "ses", "leur", "cet", "cette"}

# Les libellés de référentiel ne sont pas tous des groupes nominaux
# (« Facile », « Recherche peu efficace », « Annulation sans explication »).
# On écarte adjectifs et participes pour ne conserver que des noms utilisables
# derrière un article. Si aucun nom ne subsiste, on retombe sur le niveau 1.
_NON_NOMINAUX = {
    "facile", "difficile", "efficace", "performant", "performants", "pertinent",
    "pertinentes", "pertinents", "incomplet", "conforme", "decevante", "decevant",
    "complexe", "partiel", "partielle", "long", "longue", "eleve", "elevee",
    "inconnu", "inconnue", "incorrect", "incorrecte", "insuffisantes", "insuffisant",
    "insuffisante", "trompeuses", "fiables", "large", "difficiles", "manquante",
    "manquant", "inaccessible", "prete", "signalee", "communiquee", "unifie",
    "gerable", "exploite", "mauvaise", "different", "differente", "endommage",
    "perdu", "respecte", "acceptee", "creditees", "claires", "physique", "technique",
    "important", "promotionnels", "mobile", "personnelles", "cadeau", "libre",
}


def mots_cles(libelle: str, repli: str = "") -> list:
    """Noms porteurs d'un libellé, sans accents ni mots outils ni adjectifs.

    ``repli`` : libellé de secours (typiquement le niveau 1) si le libellé ne
    contient aucun nom exploitable.
    """
    def _extraire(txt):
        norm = unicodedata.normalize("NFKD", str(txt).lower())
        norm = "".join(c for c in norm if not unicodedata.combining(c))
        return [m for m in re.split(r"[^a-z]+", norm)
                if m and m not in _STOP and len(m) > 2]

    mots = _extraire(libelle)
    noms = [m for m in mots if m not in _NON_NOMINAUX]
    if not noms and repli:
        noms = [m for m in _extraire(repli) if m not in _NON_NOMINAUX]
    return noms or mots or ["sujet"]


# --- Accord des adjectifs -------------------------------------------------- #
_ADJ_FEM = {
    "intuitif": "intuitive", "reactif": "reactive", "clair": "claire", "lent": "lente",
    "confus": "confuse", "decevant": "decevante", "complique": "compliquee",
    "frustrant": "frustrante", "aberrant": "aberrante", "flou": "floue",
    "mal fichu": "mal fichue", "bien fait": "bien faite", "opaque": "opaque",
}


def accorder_adj(adj: str, mot_regi: str) -> str:
    """Accorde un adjectif au genre du mot qu'il qualifie."""
    if genre(mot_regi) == "m":
        return adj
    if adj in _ADJ_FEM:
        return _ADJ_FEM[adj]
    if adj.endswith("e"):
        return adj
    if adj.endswith("f"):
        return adj[:-1] + "ve"
    if adj.endswith("x"):
        return adj[:-1] + "se"
    return adj + "e"


# --- Genre grammatical -------------------------------------------------- #
# Les mots-clés sont extraits des libellés du référentiel : leur genre n'est
# pas connu a priori. Heuristique + exceptions, complétée par des tournures
# sans article (« côté X », « concernant X ») qui restent justes dans tous les cas.
_FEM_EXPLICITE = {
    "recherche", "commande", "livraison", "carte", "erreur", "lenteur", "couleur",
    "rupture", "procedure", "reponse", "photos", "regles", "nouveautes", "alerte",
    "page", "facture", "reduction", "promo", "remise", "taille", "date", "fiche",
    "boutique", "caisse", "adresse", "notification", "annulation", "connexion",
    "navigation", "ergonomie", "description", "recommandations", "donnees",
    "expedition", "reception", "attente", "gestion", "offre", "marque", "aide",
}
_MASC_EXPLICITE = {
    "probleme", "systeme", "compte", "service", "catalogue", "groupe", "article",
    "site", "code", "mode", "echange", "colis", "delai", "bug", "paiement", "prix",
    "stock", "produit", "magasin", "email", "avis", "contenu", "historique", "mot",
    "achat", "points", "frais", "remboursement", "reapprovisionnement", "suivi",
    "retrait", "panier", "vendeur", "montant", "solde", "numero", "bon", "tunnel",
}
_SUFFIXES_FEM = ("tion", "sion", "ite", "ure", "ance", "ence", "esse", "aison",
                 "ette", "elle", "ie", "te")


def genre(mot: str) -> str:
    """Retourne 'f' ou 'm' pour un mot-clé issu d'un libellé de référentiel."""
    m = str(mot).lower()
    if m in _FEM_EXPLICITE:
        return "f"
    if m in _MASC_EXPLICITE:
        return "m"
    if m.endswith(_SUFFIXES_FEM):
        return "f"
    return "m"


def est_pluriel(mot: str) -> bool:
    """Heuristique de nombre : les libellés de référentiel contiennent des pluriels
    (« Photos insuffisantes », « Points non crédités »)."""
    m = str(mot).lower()
    return m.endswith("s") and not m.endswith(("ais", "ois", "us", "as", "is", "os"))


def det(mot: str) -> str:
    """Article défini adapté au genre et au nombre."""
    m = str(mot).lower()
    if est_pluriel(m):
        return "les "
    if m[:1] in "aeiouyh":
        return "l'"
    return "la " if genre(m) == "f" else "le "


def _accord(mot: str, forme_m: str, forme_f: str) -> str:
    return forme_f if genre(mot) == "f" else forme_m


def patrons_pour(niv1: str, niv2: str) -> tuple:
    """Patrons de phrase dérivés des libellés. Générique : indépendant du référentiel.

    Les tournures sans article (« côté X », « concernant X », « X : … ») sont
    majoritaires : elles restent grammaticalement justes quel que soit le genre
    du mot-clé, ce qui rend le module robuste à tout nouveau référentiel.
    """
    mc = mots_cles(niv2, repli=niv1)
    a = mc[0]
    b = mc[1] if len(mc) > 1 else mc[0]
    t0 = mots_cles(niv1)[0]
    return {
        "Négatif": [
            "{deta} n'est pas au niveau{ctx}",
            "probleme de {a}{ctx}",
            "j'ai un souci avec {deta}{ctx}",
            "{deta} pose probleme{ctx}",
            "impossible de gerer {deta}{ctx}",
            "cote {t0}, ca ne suit pas pour {a}{ctx}",
            "rien ne fonctionne pour {a}{ctx}",
            "{dett0} est {int}{adjn}{ctx}",
            "j'ai attendu pour {a}{ctx} et personne ne repond",
            "{deta} devrait etre {revu}{ctx}",
            "aucune information sur {a}{ctx}",
            "concernant {b}, ce n'est pas ce qui etait annonce{ctx}",
            "{deta} me fait perdre du temps{ctx}",
            "je bloque sur {a}{ctx}",
            "{a} : {int}{adjn}{ctx}",
        ],
        "Positif": [
            "{deta} est {int}{adjp}{ctx}",
            "aucun souci avec {a}{ctx}",
            "{dett0} fonctionne bien{ctx}",
            "j'ai trouve {deta} {int}{adjp}{ctx}",
            "{deta} m'a fait gagner du temps{ctx}",
            "tout s'est bien passe pour {a}{ctx}",
            "{detb} est {int}{adjp}{ctx}",
            "rien a redire sur {a}{ctx}",
            "cote {t0}, c'est {int}{adjp}{ctx}",
            "{a} : {int}{adjp}{ctx}",
        ],
        "Neutre": [
            "{deta}, ca depend{ctx}",
            "{deta} pourrait etre plus {adjp}{ctx}",
            "j'ai une remarque sur {a}{ctx}",
            "{dett0} est correct sans plus{ctx}",
            "{deta} est comme d'habitude{ctx}",
            "question sur {b}{ctx}",
            "concernant {a}, ni bien ni mal{ctx}",
        ],
    }, {"a": a, "b": b, "t0": t0}


def fragment(niv1: str, niv2: str, sentiment: str, rng, patrons_surcharge=None) -> str:
    """Fragment de phrase pour un couple (thème, sous-thème, sentiment)."""
    if patrons_surcharge and (niv1, niv2) in patrons_surcharge:
        pats = patrons_surcharge[(niv1, niv2)].get(sentiment)
        if pats:
            _, subs = patrons_pour(niv1, niv2)
            pat = rng.choice(pats)
        else:
            table, subs = patrons_pour(niv1, niv2)
            pat = rng.choice(table[sentiment])
    else:
        table, subs = patrons_pour(niv1, niv2)
        pat = rng.choice(table[sentiment])
    a, b, t0 = subs["a"], subs["b"], subs["t0"]
    # L'adjectif s'accorde avec le mot que le patron met en sujet.
    regi = t0 if "{dett0}" in pat else (b if "{detb}" in pat else a)
    return (pat.replace("{deta}", det(a) + a)
               .replace("{detb}", det(b) + b)
               .replace("{dett0}", det(t0) + t0)
               .replace("{revu}", _accord(a, "revu", "revue"))
               .replace("{a}", a).replace("{b}", b).replace("{t0}", t0)
               .replace("{ctx}", rng.choice(CTX))
               .replace("{int}", rng.choice(INT_FORT + INT_FAIBLE + ["", "", ""]))
               .replace(" est ", " sont " if est_pluriel(regi) else " est ")
               .replace("{adjn}", accorder_adj(rng.choice(ADJ_NEG), regi))
               .replace("{adjp}", accorder_adj(rng.choice(ADJ_POS), regi)))


def composer(themes, rng, bruit=True, longueur=None, patrons_surcharge=None) -> str:
    """Compose un verbatim.

    ``themes`` : liste de 1 ou 2 tuples ``(niv1, niv2, sentiment)``.
    ``longueur`` : ``None`` | ``"long"`` | ``"court"``.
    """
    if longueur == "court":
        return rng.choice(TRES_COURT)

    frags = [fragment(n1, n2, s, rng, patrons_surcharge) for n1, n2, s in themes]
    sents = [s for _, _, s in themes]

    if len(frags) == 2:
        divergent = sents[0] != sents[1] and "Neutre" not in sents
        lien = rng.choice(ADVERS) if (divergent and rng.random() < 0.70) \
            else rng.choice(NEUTRE_LIEN)
        corps = frags[0] + lien + frags[1]
    else:
        corps = frags[0]

    ouv = {"Négatif": OUV_NEG, "Positif": OUV_POS, "Neutre": OUV_NEU}[sents[0]]
    clo = {"Négatif": CLO_NEG, "Positif": CLO_POS, "Neutre": CLO_NEU}[sents[-1]]
    texte = rng.choice(ouv) + corps + rng.choice(clo)
    if not texte.endswith((".", "!", "?")):
        texte += "."

    if longueur == "long":
        texte += " " + " ".join(rng.choice(QUEUE_LONGUE) for _ in range(rng.randint(4, 8)))

    texte = _accentuer(texte)
    if bruit and rng.random() < 0.20:
        texte = _bruiter(texte, rng)
    if texte and texte[0].islower():
        texte = texte[0].upper() + texte[1:]
    return texte
