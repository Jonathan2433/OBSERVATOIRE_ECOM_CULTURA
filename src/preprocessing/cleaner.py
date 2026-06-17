"""Nettoyage du texte des verbatims.

Étapes (toutes pilotées par ``config.yaml`` -> section ``cleaning``) :
  - normalisation Unicode (NFKC) ;
  - suppression des emojis et symboles non textuels ;
  - passage en minuscules (optionnel — voir note sur CamemBERT) ;
  - normalisation des espaces ;
  - filtre de longueur min (verbatims trop courts) / max.

NOTE : CamemBERT-base est un modèle *cased* (sensible à la casse). Le passage en
minuscules est donc un choix piloté par config (``cleaning.lowercase``). Il est
conservé ici car explicitement demandé au cahier des charges et homogénéise les
verbatims bruités ; pour maximiser la performance on peut le désactiver.
Les accents sont TOUJOURS préservés (essentiels en français).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

import pandas as pd

# Plage d'emojis et de symboles graphiques (pictogrammes, drapeaux, etc.).
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # symboles & pictogrammes divers, emojis
    "\U00002600-\U000027BF"  # symboles divers + dingbats
    "\U0001F000-\U0001F0FF"  # tuiles mahjong / dominos / cartes
    "\U00002190-\U000021FF"  # flèches
    "\U00002B00-\U00002BFF"  # symboles & flèches supplémentaires
    "\U0000FE00-\U0000FE0F"  # sélecteurs de variation
    "\U0001F1E6-\U0001F1FF"  # indicateurs régionaux (drapeaux)
    "]+",
    flags=re.UNICODE,
)

# Espaces multiples / sauts de ligne.
_WHITESPACE_PATTERN = re.compile(r"\s+")


class TextCleaner:
    """Nettoyeur de texte paramétré par la configuration."""

    def __init__(self, cfg: Dict[str, Any]):
        conf = cfg.get("cleaning", {})
        self.lowercase: bool = conf.get("lowercase", True)
        self.remove_emojis: bool = conf.get("remove_emojis", True)
        self.normalize_unicode: bool = conf.get("normalize_unicode", True)
        self.min_tokens: int = conf.get("min_tokens", 5)
        self.max_tokens: int = conf.get("max_tokens", 512)

    # ------------------------------------------------------------------ #
    def clean(self, text: Any) -> str:
        """Nettoie une chaîne. Renvoie "" pour les valeurs vides/NaN."""
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return ""
        text = str(text)

        if self.normalize_unicode:
            text = unicodedata.normalize("NFKC", text)
        if self.remove_emojis:
            text = _EMOJI_PATTERN.sub(" ", text)
        if self.lowercase:
            text = text.lower()

        # Normalisation des espaces.
        text = _WHITESPACE_PATTERN.sub(" ", text).strip()

        # Troncature douce en nombre de "mots" (le modèle re-tronque ensuite à
        # max_length tokens lors de la tokenisation CamemBERT).
        tokens = text.split(" ")
        if len(tokens) > self.max_tokens:
            text = " ".join(tokens[: self.max_tokens])
        return text

    # ------------------------------------------------------------------ #
    @staticmethod
    def count_tokens(text: str) -> int:
        """Approximation du nombre de tokens par découpage sur les espaces."""
        if not text:
            return 0
        return len(text.split())

    def is_too_short(self, text: str) -> bool:
        """True si le verbatim est sous le seuil minimal de tokens."""
        return self.count_tokens(text) < self.min_tokens

    def is_empty(self, text: str) -> bool:
        return text is None or str(text).strip() == ""
