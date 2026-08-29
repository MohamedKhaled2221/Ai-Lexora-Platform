from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(
    name: str,
    default: bool,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class Settings:
    """
    Central configuration for M5.

    Environment variables can override the defaults.

    Current M5 integration:
        - LegalBERT/AraLegal-BERT sequence classification
        - lexical similarity fallback
        - optional sentence-transformer similarity
        - lexical similarity fallback
        - optional sentence-transformer similarity
    """

    # -------------------------------------------------------------
    # Future classifier model configuration
    # -------------------------------------------------------------
    #
    # These are reserved for a future evaluation of:
    #   LegalBERT / AraLegal-BERT
    #
    # The current ClauseClassifier does not load these models.

    english_classifier_model: str = os.getenv(
        "M5_ENGLISH_CLASSIFIER_MODEL",
        "",
    )

    arabic_classifier_model: str = os.getenv(
        "M5_ARABIC_CLASSIFIER_MODEL",
        "",
    )

    # -------------------------------------------------------------
    # Similarity backend
    # -------------------------------------------------------------

    similarity_model: str = os.getenv(
        "M5_SIMILARITY_MODEL",
        "",
    )

    use_sentence_transformers: bool = _bool(
        "M5_USE_SENTENCE_TRANSFORMERS",
        False,
    )

    # -------------------------------------------------------------
    # Classification
    # -------------------------------------------------------------

    classification_threshold: float = float(
        os.getenv(
            "M5_CLASSIFICATION_THRESHOLD",
            "0.45",
        )
    )

    use_transformers: bool = _bool(
        "M5_USE_TRANSFORMERS",
        True,
    )

    # -------------------------------------------------------------
    # Reference similarity
    # -------------------------------------------------------------

    similarity_threshold: float = float(
        os.getenv(
            "M5_SIMILARITY_THRESHOLD",
            "0.70",
        )
    )

    # -------------------------------------------------------------
    # Analysis input limit
    # -------------------------------------------------------------
    #
    # This limit is used for bounded analysis operations.
    # The original clause text is still preserved in ContractClause.

    max_text_chars: int = int(
        os.getenv(
            "M5_MAX_TEXT_CHARS",
            "20000",
        )
    )


settings = Settings()