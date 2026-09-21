"""Anonymisation des données personnelles (PII) AVANT tout traitement.

Contrainte RGPD du POC : aucune donnée personnelle ne doit être tokenisée ni
intégrée dans les poids du modèle. L'anonymisation est donc appliquée en TÊTE
de pipeline, avant le nettoyage et l'inférence.

Entités masquées (configurable via ``anonymization.entities_to_mask``) :
  - EMAIL    : adresses e-mail            -> [EMAIL]
  - PHONE    : numéros de téléphone FR    -> [TEL]
  - ORDER_ID : numéros de commande/réf.   -> [COMMANDE]
  - PER      : noms propres (NER spaCy)   -> [NOM]

L'ordre est important : on masque d'abord par regex (emails, téléphones, n° de
commande) PUIS on applique la NER sur le texte déjà partiellement masqué.

Robustesse : si le modèle spaCy n'est pas installé, l'anonymiseur fonctionne en
mode dégradé (regex seules) et émet un avertissement — la NER (noms propres) est
alors désactivée. En production, ``setup_models.py`` installe le modèle spaCy.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Expressions régulières PII
# --------------------------------------------------------------------------- #
# E-mail (RFC simplifiée, suffisante pour des verbatims).
# L'astérisque est admis dans la partie locale : Cultura masque parfois ses
# exports en amont, mais **incomplètement** — 10 occurrences de la forme
# `******@free.fr` mesurées le 09/09/2026, que l'ancien motif laissait passer
# (le domaine, lui, reste une donnée personnelle). `\b` est remplacé par un
# lookbehind : il n'y a pas de frontière de mot devant un `*`.
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-*])[A-Za-z0-9._%+\-*]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Téléphone français : 0X XX XX XX XX, +33 / 0033, séparateurs espace/point/tiret.
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:(?:\+|00)33[\s.\-]?(?:\(0\))?|0)"   # indicatif +33 / 0033 / 0
    r"\d(?:[\s.\-]?\d{2}){4}"                  # 9 chiffres groupés par 2
    r"(?!\d)"
)

# Numéro de commande / référence : mot-clé explicite suivi d'un identifiant,
# OU code alphanumérique mêlant lettres et chiffres (ex. CMD12345, FR-2024-0099).
_ORDER_KEYWORD_RE = re.compile(
    r"\b(?:commande|cmd|réf|ref|référence|order|n[°o]|numéro)\s*[:#]?\s*"
    r"([A-Za-z]{0,4}[\-\s]?\d{4,}[A-Za-z0-9\-]*)",
    flags=re.IGNORECASE,
)
# Codes alphanumériques autonomes (au moins une lettre ET >=4 chiffres).
_ORDER_CODE_RE = re.compile(r"\b(?=[A-Za-z0-9\-]*[A-Za-z])(?=[A-Za-z0-9\-]*\d{4,})[A-Za-z0-9\-]{6,}\b")
# Longues suites de chiffres autonomes (>=6) = probablement un n° de commande.
_LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{6,}(?!\d)")

# --------------------------------------------------------------------------- #
#  Anti-faux-positifs NER
# --------------------------------------------------------------------------- #
# Le petit modèle spaCy fr_core_news_sm sur-détecte des PER : il étiquette
# fréquemment des noms communs e-commerce en début de phrase ("Livraison",
# "Colis"...) comme des personnes. Les masquer DÉTRUIRAIT le signal thématique.
# On protège donc une liste de vocabulaire métier : ces tokens ne sont jamais
# masqués comme noms propres, même si spaCy les étiquette PER. (Extensible via
# ``anonymization.per_stoplist`` dans config.yaml.)
_PER_STOPLIST = {
    # Logistique / commande
    "livraison", "commande", "colis", "stock", "rupture", "retour", "remboursement",
    "préparation", "expédition", "transporteur", "retrait",
    # Site / techno
    "site", "application", "appli", "navigation", "page", "panier", "compte",
    "connexion", "paiement", "bug", "lenteur", "ergonomie", "internet", "mobile",
    "click", "collect", "magasin", "boutique", "catalogue", "référence", "article",
    # Marketing / contenu
    "promotion", "promo", "réduction", "carte", "cadeau", "email", "mail",
    "newsletter", "fidélité", "points", "avis", "photo", "photos", "fiche",
    "produit", "produits", "prix", "frais", "service", "client",
    # Politesse / appréciations fréquentes (souvent en tête de phrase, capitalisées)
    "bonjour", "bonsoir", "merci", "cordialement", "madame", "monsieur",
    "top", "super", "nickel", "parfait", "génial", "rapide", "conforme",
    "décevant", "lent", "facile", "intuitive", "intuitif",
    # Enseigne (à protéger pour ne pas dégrader les signaux)
    "cultura",
    # Délai (remontée métier 21/09/2026 : "Délai long pour un article
    # présent en magasin" masqué en "[NOM] long..." — majuscule de début
    # de phrase, faux positif documenté en R-14).
    "délai", "délais",
}

# Élisions françaises ("n'", "qu'", "m'"...) que spaCy scinde en token à part
# et que le petit modèle `fr_core_news_sm` étiquette parfois PER à tort
# (remontée métier 21/09/2026 : "cela n'est pas rattrapable" -> "cela
# [NOM]est pas rattrapable" ; "qu'une pièce d'identité" -> "[NOM]une pièce
# d'identité"). Une élision seule ne peut jamais être un nom propre : le
# span entier doit être une des formes listées, apostrophe droite ou
# typographique.
_ELISION_RE = re.compile(
    r"^(?:jusqu|lorsqu|puisqu|quoiqu|qu|[cdjlmnst])['’]$", re.IGNORECASE
)


def _is_stoplisted(span_text: str, stoplist: set) -> bool:
    """True si tous les tokens du span sont du vocabulaire métier (à ne pas masquer)."""
    tokens = [t for t in re.split(r"\s+", span_text.strip().lower()) if t]
    return bool(tokens) and all(t in stoplist for t in tokens)


def _is_elision_fragment(span_text: str) -> bool:
    """True si le span n'est qu'une élision française (n', qu', d'...), jamais un nom."""
    return bool(_ELISION_RE.match(span_text.strip()))


class AnonymisationIndisponibleError(RuntimeError):
    """spaCy est requis mais absent : le masquage des noms propres serait muet.

    Levée par :func:`verifier_ner_disponible`, appelée **au démarrage** du
    chargeur (§10.3 de SPEC_CHARGEUR). Le mode dégradé du constructeur est
    conservé — il est légitime pour les recettes applicatives torch-free, qui
    n'ingèrent aucune donnée réelle — mais il ne doit jamais s'appliquer
    silencieusement à une chaîne qui touche des verbatims Cultura.
    """


def verifier_ner_disponible(cfg: Dict[str, Any]) -> None:
    """Échoue si l'anonymisation des noms propres est demandée mais indisponible.

    Contrôle explicite exigé par §10.3 : le mode dégradé de spaCy est silencieux
    (T5, R-14), et les 302 masquages `[NOM]` du prototype étaient très
    probablement des faux positifs sur des majuscules de début de phrase. Un
    masquage muet des noms propres est un risque RGPD, pas un désagrément.

    Désactivable délibérément par ``anonymization.require_spacy: false``.
    """
    anon = cfg.get("anonymization", {}) or {}
    if not anon.get("enabled", True):
        return
    if not anon.get("require_spacy", True):
        return
    if "PER" not in set(anon.get("entities_to_mask", [])):
        return
    modele = anon.get("spacy_model", "fr_core_news_sm")
    try:
        import spacy

        spacy.load(modele, disable=["lemmatizer", "tagger", "parser"])
    except Exception as exc:  # noqa: BLE001 - dépend de l'environnement
        raise AnonymisationIndisponibleError(
            f"`anonymization.enabled` est vrai et `PER` fait partie des entités à "
            f"masquer, mais le modèle spaCy '{modele}' est indisponible "
            f"({type(exc).__name__}: {exc}). Les noms propres ne seraient PAS "
            f"masqués, en silence. Installer le modèle "
            f"(`python -m spacy download {modele}`), ou assumer explicitement le "
            f"mode dégradé via `anonymization.require_spacy: false`."
        ) from exc


class Anonymizer:
    """Masque les PII d'un texte et compte les entités supprimées."""

    def __init__(self, cfg: Dict[str, Any]):
        anon = cfg.get("anonymization", {})
        self.enabled: bool = anon.get("enabled", True)
        self.entities = set(anon.get("entities_to_mask", ["PER", "EMAIL", "PHONE", "ORDER_ID"]))
        self.masks: Dict[str, str] = anon.get(
            "mask_tokens",
            {"PER": "[NOM]", "EMAIL": "[EMAIL]", "PHONE": "[TEL]", "ORDER_ID": "[COMMANDE]"},
        )
        self.spacy_model_name: str = anon.get("spacy_model", "fr_core_news_sm")
        # Stoplist anti-faux-positifs (built-in + extension config).
        self.per_stoplist = set(_PER_STOPLIST) | {
            w.lower() for w in anon.get("per_stoplist", [])
        }
        self._nlp = None
        self._ner_available = False
        if self.enabled and "PER" in self.entities:
            self._load_spacy()

    # ------------------------------------------------------------------ #
    def _load_spacy(self) -> None:
        """Charge le modèle spaCy une seule fois (mode dégradé si absent)."""
        try:
            import spacy

            self._nlp = spacy.load(self.spacy_model_name, disable=["lemmatizer", "tagger", "parser"])
            self._ner_available = True
            logger.info("Modèle spaCy '%s' chargé pour la NER (noms propres).", self.spacy_model_name)
        except Exception as exc:  # pragma: no cover - dépend de l'environnement
            self._ner_available = False
            logger.warning(
                "Modèle spaCy '%s' indisponible (%s) : anonymisation des NOMS PROPRES "
                "désactivée. Installez-le via `python -m spacy download %s`. "
                "Les e-mails, téléphones et n° de commande restent masqués (regex).",
                self.spacy_model_name, type(exc).__name__, self.spacy_model_name,
            )

    # ------------------------------------------------------------------ #
    def anonymize(self, text: Any) -> Tuple[str, Counter]:
        """Anonymise un texte. Renvoie (texte_masqué, compteur_par_entité)."""
        counts: Counter = Counter()
        if not self.enabled or text is None:
            return ("" if text is None else str(text), counts)
        text = str(text)
        if text.strip() == "":
            return "", counts

        # --- 1. Regex (ordre : email > téléphone > commande) -----------------
        if "EMAIL" in self.entities:
            text, n = _EMAIL_RE.subn(self.masks["EMAIL"], text)
            counts["EMAIL"] += n
        if "PHONE" in self.entities:
            text, n = _PHONE_RE.subn(self.masks["PHONE"], text)
            counts["PHONE"] += n
        if "ORDER_ID" in self.entities:
            tok = self.masks["ORDER_ID"]
            text, n1 = _ORDER_KEYWORD_RE.subn(lambda m: tok, text)
            text, n2 = _ORDER_CODE_RE.subn(tok, text)
            text, n3 = _LONG_DIGITS_RE.subn(tok, text)
            counts["ORDER_ID"] += n1 + n2 + n3

        # --- 2. NER spaCy (noms de personnes) --------------------------------
        if "PER" in self.entities and self._ner_available:
            text, n = self._mask_persons(text)
            counts["PER"] += n

        return text, counts

    # ------------------------------------------------------------------ #
    def _mask_persons(self, text: str) -> Tuple[str, int]:
        """Remplace les entités PER détectées par spaCy. Renvoie (texte, n)."""
        doc = self._nlp(text)
        # On ne garde que les PER qui ne sont PAS du vocabulaire métier protégé,
        # afin d'éviter de masquer "Livraison", "Colis"... (faux positifs spaCy).
        spans = [
            ent for ent in doc.ents
            if ent.label_ == "PER"
            and not _is_stoplisted(ent.text, self.per_stoplist)
            and not _is_elision_fragment(ent.text)
        ]
        if not spans:
            return text, 0
        tok = self.masks["PER"]
        chars = list(text)
        for ent in sorted(spans, key=lambda e: e.start_char, reverse=True):
            chars[ent.start_char:ent.end_char] = list(tok)
        return "".join(chars), len(spans)
