"""Architecture des modèles, versioning, embeddings et backends d'inférence.

CHOIX D'ARCHITECTURE (justifié dans train_classifier.py) :
  - On utilise les têtes STANDARD HuggingFace ``AutoModelForSequenceClassification``
    plutôt que des têtes custom. Raison : optimum exporte/quantifie en ONNX int8
    sans friction les architectures standard. Une tête custom (ex. concaténer le
    score de satisfaction à l'embedding [CLS]) casserait cet export ; on injecte
    donc les signaux auxiliaires au niveau du texte (préfixe), pas de l'architecture.

VERSIONING (contrainte "timestamp dans le nom de fichier") :
  Chaque modèle est sauvegardé dans un sous-dossier horodaté
  ``<base>/<YYYYMMDD_HHMMSS>/`` et un fichier ``<base>/CURRENT`` pointe vers la
  version active. L'inférence résout le dossier via ``resolve_model_dir``.

BACKENDS D'INFÉRENCE :
  - ``TorchSeqClassifier`` : PyTorch (fallback universel).
  - ``OnnxSeqClassifier``  : ONNX Runtime int8 (rapide sur CPU, défaut si dispo).
  Les deux exposent la même API ``predict_proba(texts) -> np.ndarray``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..utils.config import resolve_device, resolve_path

logger = logging.getLogger(__name__)

CURRENT_POINTER = "CURRENT"
ONNX_SUBDIR = "onnx_int8"


def onnx_model_file(onnx_dir: Path):
    """Nom du fichier ONNX à utiliser (quantifié int8 prioritaire), ou None."""
    onnx_dir = Path(onnx_dir)
    for name in ("model_quantized.onnx", "model.onnx"):
        if (onnx_dir / name).is_file():
            return name
    return None


# --------------------------------------------------------------------------- #
#  Chemins / source du modèle de base
# --------------------------------------------------------------------------- #
def base_model_path(cfg: Dict[str, Any]) -> str:
    """Chemin du modèle de base : dossier local si présent (hors ligne), sinon nom HF.

    Après ``setup_models.py``, les poids CamemBERT vivent en local et tout
    fonctionne sans réseau (``local_files_only`` côté transformers).
    """
    local = resolve_path(cfg, cfg["model"]["local_model_dir"])
    if local.is_dir() and any(local.iterdir()):
        return str(local)
    return cfg["model"]["base_model"]


def _is_local(path: str) -> bool:
    return Path(path).is_dir()


# --------------------------------------------------------------------------- #
#  Tokenizer / modèle
# --------------------------------------------------------------------------- #
def load_tokenizer(model_path: str):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_path, local_files_only=_is_local(model_path))


def build_sequence_classifier(base_path: str, num_labels: int, multilabel: bool):
    """Construit une tête de classification standard sur CamemBERT.

    ``multilabel=True`` -> problem_type multi_label (sigmoid + BCE) pour niv.1.
    ``multilabel=False`` -> single_label (softmax + CE) pour niv.2 et sentiment.
    """
    from transformers import AutoModelForSequenceClassification

    problem_type = "multi_label_classification" if multilabel else "single_label_classification"
    return AutoModelForSequenceClassification.from_pretrained(
        base_path,
        num_labels=num_labels,
        problem_type=problem_type,
        local_files_only=_is_local(base_path),
    )


# --------------------------------------------------------------------------- #
#  Versioning horodaté
# --------------------------------------------------------------------------- #
def save_versioned(model, tokenizer, base_dir: Path, card: Dict[str, Any]) -> Path:
    """Sauvegarde le modèle dans un sous-dossier horodaté et met à jour CURRENT."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_dir = base_dir / ts
    version_dir.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(version_dir)
    tokenizer.save_pretrained(version_dir)
    card = dict(card)
    card["version"] = ts
    card["saved_at"] = datetime.now().isoformat(timespec="seconds")
    with open(version_dir / "training_card.json", "w", encoding="utf-8") as fh:
        json.dump(card, fh, ensure_ascii=False, indent=2)

    (base_dir / CURRENT_POINTER).write_text(ts, encoding="utf-8")
    logger.info("Modèle sauvegardé (version %s) dans %s", ts, version_dir)
    return version_dir


def resolve_model_dir(base_dir: Path) -> Path:
    """Résout le dossier de la version active via le pointeur CURRENT.

    Si ``CURRENT`` est absent, renvoie ``base_dir`` directement (tolérant).
    """
    base_dir = Path(base_dir)
    pointer = base_dir / CURRENT_POINTER
    if pointer.is_file():
        ts = pointer.read_text(encoding="utf-8").strip()
        cand = base_dir / ts
        if cand.is_dir():
            return cand
    return base_dir


# --------------------------------------------------------------------------- #
#  Backend PyTorch
# --------------------------------------------------------------------------- #
class TorchSeqClassifier:
    """Classifieur de séquence PyTorch (fallback universel)."""

    def __init__(self, model, tokenizer, multilabel: bool, max_length: int, device: str):
        import torch

        self.torch = torch
        self.model = model.to(device).eval()
        self.tokenizer = tokenizer
        self.multilabel = multilabel
        self.max_length = max_length
        self.device = device

    @classmethod
    def from_dir(cls, model_dir: Path, multilabel: bool, cfg: Dict[str, Any]):
        from transformers import AutoModelForSequenceClassification

        model_dir = resolve_model_dir(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_dir, local_files_only=True
        )
        tokenizer = load_tokenizer(str(model_dir))
        max_length = _effective_max_length(cfg)
        return cls(model, tokenizer, multilabel, max_length, resolve_device(cfg))

    def predict_proba(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        torch = self.torch
        probs: List[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                enc = self.tokenizer(
                    batch, truncation=True, max_length=self.max_length,
                    padding=True, return_tensors="pt",
                ).to(self.device)
                logits = self.model(**enc).logits
                if self.multilabel:
                    p = torch.sigmoid(logits)
                else:
                    p = torch.softmax(logits, dim=-1)
                probs.append(p.cpu().numpy())
        return np.concatenate(probs, axis=0) if probs else np.zeros((0, 0))


# --------------------------------------------------------------------------- #
#  Backend ONNX Runtime (int8)
# --------------------------------------------------------------------------- #
class OnnxSeqClassifier:
    """Classifieur de séquence ONNX Runtime quantifié int8 (CPU rapide)."""

    def __init__(self, model, tokenizer, multilabel: bool, max_length: int):
        self.model = model
        self.tokenizer = tokenizer
        self.multilabel = multilabel
        self.max_length = max_length

    @classmethod
    def from_dir(cls, model_dir: Path, multilabel: bool, cfg: Dict[str, Any]):
        from optimum.onnxruntime import ORTModelForSequenceClassification

        onnx_dir = resolve_model_dir(model_dir) / ONNX_SUBDIR
        # Privilégie le modèle quantifié int8 ('model_quantized.onnx'), sinon
        # le modèle ONNX non quantifié ('model.onnx').
        file_name = onnx_model_file(onnx_dir)
        if file_name is None:
            raise FileNotFoundError(f"Aucun modèle ONNX dans {onnx_dir}")
        model = ORTModelForSequenceClassification.from_pretrained(onnx_dir, file_name=file_name)
        tokenizer = load_tokenizer(str(onnx_dir))
        return cls(model, tokenizer, multilabel, _effective_max_length(cfg))

    def predict_proba(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        probs: List[np.ndarray] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # return_tensors='pt' : convention optimum (ORTModel renvoie des
            # tenseurs torch) ; on reconvertit ensuite en numpy.
            enc = self.tokenizer(
                batch, truncation=True, max_length=self.max_length,
                padding=True, return_tensors="pt",
            )
            logits = self.model(**enc).logits
            logits = logits.detach().cpu().numpy() if hasattr(logits, "detach") else np.asarray(logits)
            if self.multilabel:
                p = 1.0 / (1.0 + np.exp(-logits))
            else:
                e = np.exp(logits - logits.max(axis=-1, keepdims=True))
                p = e / e.sum(axis=-1, keepdims=True)
            probs.append(p)
        return np.concatenate(probs, axis=0) if probs else np.zeros((0, 0))


# --------------------------------------------------------------------------- #
#  Extraction d'embeddings (détecteurs de signaux)
# --------------------------------------------------------------------------- #
class EmbeddingExtractor:
    """Embeddings CamemBERT GELÉS (mean/cls pooling) pour les signaux.

    Utilisé à l'identique à l'entraînement (train_signals) et à l'inférence
    (predictor) afin de garantir la cohérence des features de la LogReg.
    """

    def __init__(self, cfg: Dict[str, Any]):
        import torch
        from transformers import AutoModel

        self.torch = torch
        self.cfg = cfg
        self.pooling = cfg.get("signals", {}).get("pooling", "mean")
        self.max_length = _effective_max_length(cfg)
        self.device = resolve_device(cfg)
        base = base_model_path(cfg)
        self.tokenizer = load_tokenizer(base)
        self.model = AutoModel.from_pretrained(base, local_files_only=_is_local(base))
        self.model = self.model.to(self.device).eval()

    def embed(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        torch = self.torch
        out: List[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                enc = self.tokenizer(
                    batch, truncation=True, max_length=self.max_length,
                    padding=True, return_tensors="pt",
                ).to(self.device)
                hidden = self.model(**enc).last_hidden_state  # (B, T, H)
                if self.pooling == "cls":
                    pooled = hidden[:, 0, :]
                else:  # mean pooling masqué
                    mask = enc["attention_mask"].unsqueeze(-1).type_as(hidden)
                    pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                out.append(pooled.cpu().numpy())
        return np.concatenate(out, axis=0) if out else np.zeros((0, 0))


# --------------------------------------------------------------------------- #
#  Export ONNX + quantization int8
# --------------------------------------------------------------------------- #
def export_onnx_int8(model_dir: Path, cfg: Dict[str, Any]) -> Optional[Path]:
    """Exporte la version active d'un modèle en ONNX et la quantifie en int8.

    Quantization DYNAMIQUE (is_static=False) : aucune donnée de calibration
    requise, idéale pour un POC. Renvoie le dossier ONNX ou None si désactivé.
    """
    if not cfg.get("onnx", {}).get("enabled", True):
        return None
    try:
        from optimum.onnxruntime import ORTModelForSequenceClassification, ORTQuantizer
        from optimum.onnxruntime.configuration import AutoQuantizationConfig
    except ImportError:
        logger.warning("optimum non installé : export ONNX ignoré.")
        return None

    version_dir = resolve_model_dir(model_dir)
    onnx_dir = version_dir / ONNX_SUBDIR
    onnx_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Export ONNX de %s ...", version_dir)
    ort_model = ORTModelForSequenceClassification.from_pretrained(version_dir, export=True)
    ort_model.save_pretrained(onnx_dir)
    load_tokenizer(str(version_dir)).save_pretrained(onnx_dir)

    if cfg["onnx"].get("quantize_int8", True):
        logger.info("Quantization int8 (dynamique) ...")
        quantizer = ORTQuantizer.from_pretrained(onnx_dir)
        # avx2 : compatible large parc CPU (x86). Dynamique = sans calibration.
        qconfig = AutoQuantizationConfig.avx2(is_static=False, per_channel=False)
        quantizer.quantize(save_dir=onnx_dir, quantization_config=qconfig)
        logger.info("Modèle int8 écrit dans %s (model_quantized.onnx).", onnx_dir)
    return onnx_dir


# --------------------------------------------------------------------------- #
#  Factory de chargement (choisit ONNX si dispo, sinon PyTorch)
# --------------------------------------------------------------------------- #
def load_classifier(model_base_dir: Path, multilabel: bool, cfg: Dict[str, Any]):
    """Charge un classifieur en privilégiant le backend ONNX int8 si configuré."""
    model_base_dir = Path(model_base_dir)
    want_onnx = cfg.get("onnx", {}).get("use_for_inference", True)
    if want_onnx:
        onnx_dir = resolve_model_dir(model_base_dir) / ONNX_SUBDIR
        if onnx_model_file(onnx_dir) is not None:
            try:
                clf = OnnxSeqClassifier.from_dir(model_base_dir, multilabel, cfg)
                logger.info("Backend ONNX chargé pour %s", model_base_dir.name)
                return clf
            except Exception as exc:  # pragma: no cover
                logger.warning("Chargement ONNX échoué (%s) -> fallback PyTorch.", exc)
    return TorchSeqClassifier.from_dir(model_base_dir, multilabel, cfg)


# --------------------------------------------------------------------------- #
def _effective_max_length(cfg: Dict[str, Any]) -> int:
    """max_length effectif (réduit en mode smoke test)."""
    if cfg.get("smoke_test", {}).get("enabled"):
        return cfg["smoke_test"].get("max_length", cfg["model"]["max_length"])
    return cfg["model"]["max_length"]
