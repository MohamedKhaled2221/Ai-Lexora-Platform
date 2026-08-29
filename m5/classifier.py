from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

from .normalizer import normalize_for_match
from .schemas import ClauseType


# Rule-assisted baseline.
# Deterministic and transparent.
#
# This is a baseline, not the final production classifier.
# A fine-tuned LegalBERT / AraLegal-BERT model can be evaluated later.

KEYWORDS: Dict[ClauseType, List[str]] = {
    ClauseType.TERMINATION: [
        "termination",
        "terminate",
        "terminated",
        "termination for cause",
        "termination without cause",
        "إنهاء",
        "فسخ",
        "انهاء",
        "إنهاء العقد",
    ],

    ClauseType.LIABILITY: [
        "liability",
        "liable",
        "limitation of liability",
        "مسؤولية",
        "مسئولية",
    ],

    ClauseType.PAYMENT: [
        "payment",
        "payable",
        "fee",
        "fees",
        "invoice",
        "amount due",
        "السداد",
        "الدفع",
        "الأتعاب",
        "مقابل",
    ],

    ClauseType.CONFIDENTIALITY: [
        "confidential",
        "confidentiality",
        "non-disclosure",
        "سرية",
        "معلومات سرية",
        "عدم الإفصاح",
    ],

    ClauseType.RENEWAL: [
        "renewal",
        "renew",
        "automatically renew",
        "auto-renew",
        "تجديد",
        "يتجدد",
        "التجديد التلقائي",
    ],

    ClauseType.PENALTY: [
        "penalty",
        "liquidated damages",
        "fine",
        "غرامة",
        "جزاء",
        "شرط جزائي",
    ],

    ClauseType.GOVERNING_LAW: [
        "governing law",
        "applicable law",
        "laws of",
        "القانون الواجب التطبيق",
        "القانون الحاكم",
    ],

    ClauseType.DISPUTE_RESOLUTION: [
        "dispute",
        "arbitration",
        "jurisdiction",
        "court",
        "نزاع",
        "تحكيم",
        "اختصاص",
        "محكمة",
    ],

    ClauseType.INDEMNITY: [
        "indemnify",
        "indemnification",
        "تعويض",
        "التعويض",
    ],

    ClauseType.INTELLECTUAL_PROPERTY: [
        "intellectual property",
        "copyright",
        "trademark",
        "patent",
        "الملكية الفكرية",
        "حقوق الملكية",
    ],

    ClauseType.FORCE_MAJEURE: [
        "force majeure",
        "act of god",
        "القوة القاهرة",
        "الظروف الطارئة",
    ],

    ClauseType.TERM: [
        "term of this agreement",
        "term and duration",
        "effective date",
        "مدة العقد",
        "مدة الاتفاقية",
        "تاريخ السريان",
    ],

    ClauseType.NOTICE: [
        "notice",
        "written notice",
        "إخطار",
        "إشعار",
    ],

    ClauseType.ASSIGNMENT: [
        "assignment",
        "assign this agreement",
        "التنازل",
        "حوالة",
    ],

    ClauseType.REPRESENTATIONS: [
        "represents",
        "representation",
        "representations",
        "يقر",
        "إقرار",
    ],

    ClauseType.WARRANTIES: [
        "warranty",
        "warranties",
        "warrants",
        "ضمان",
        "ضمانات",
    ],

    ClauseType.DATA_PROTECTION: [
        "personal data",
        "data protection",
        "privacy",
        "personal information",
        "حماية البيانات",
        "البيانات الشخصية",
        "الخصوصية",
    ],
}


class ClauseClassifier:
    """LegalBERT/AraLegal-BERT sequence classifier for M5 clauses.

    Returns `(clause_type, model_confidence, classification_metadata)`.

    Confidence is the maximum softmax probability from the selected
    sequence-classification checkpoint; it is not calibration evidence.

    M6 owns final legal risk decisions.
    """

    def __init__(
        self,
        threshold: float = 0.45,
        english_model: str = "",
        arabic_model: str = "",
        use_transformers: bool = True,
    ):
        self.threshold = threshold
        self.english_model = english_model
        self.arabic_model = arabic_model
        self.use_transformers = use_transformers
        self._models: Dict[str, Tuple[object, object]] = {}

    def classify(
        self,
        text: str,
        title: str | None = None,
        language: str = "unknown",
    ) -> Tuple[ClauseType, float, Dict]:
        if not self.use_transformers:
            raise RuntimeError(
                "Transformer classification is disabled. Set "
                "M5_USE_TRANSFORMERS=true."
            )

        model_name, language_used = self._select_model(text, language)

        if not model_name:
            raise RuntimeError(
                f"No LegalBERT classifier model is configured for language "
                f"'{language_used}'. Set M5_ENGLISH_CLASSIFIER_MODEL or "
                "M5_ARABIC_CLASSIFIER_MODEL to a fine-tuned checkpoint."
            )

        tokenizer, model = self._load_model(model_name)

        import torch

        input_text = text or ""
        if title:
            input_text = f"{title}\n{input_text}"

        inputs = tokenizer(
            input_text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )

        with torch.no_grad():
            logits = model(**inputs).logits

        probabilities = torch.softmax(logits, dim=-1)[0]
        label_id = int(torch.argmax(probabilities).item())
        confidence = float(probabilities[label_id].item())
        label = self._label_for_id(model, label_id)
        clause_type = self._clause_type_for_label(label)

        return (
            clause_type,
            round(confidence, 6),
            {
                "method": "transformer_sequence_classification",
                "model": model_name,
                "language": language_used,
                "label": label,
                "label_id": label_id,
            },
        )

    def _select_model(
        self,
        text: str,
        language: str,
    ) -> Tuple[str, str]:
        language_value = str(language or "unknown").lower()

        if language_value == "ar":
            return self.arabic_model, "ar"

        if language_value == "en":
            return self.english_model, "en"

        if language_value == "ar-en":
            arabic_count = len(re.findall(r"[\u0600-\u06FF]", text or ""))
            latin_count = len(re.findall(r"[A-Za-z]", text or ""))
            if arabic_count >= latin_count:
                return self.arabic_model, "ar"
            return self.english_model, "en"

        return self.english_model or self.arabic_model, "en" if self.english_model else "ar"

    def _load_model(self, model_name: str) -> Tuple[object, object]:
        if model_name in self._models:
            return self._models[model_name]

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as error:
            raise RuntimeError(
                "Transformer classification requires the 'transformers' package."
            ) from error

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        model.eval()
        self._models[model_name] = (tokenizer, model)
        return tokenizer, model

    @staticmethod
    def _label_for_id(model: object, label_id: int) -> str:
        config = getattr(model, "config", None)
        id_to_label = getattr(config, "id2label", {}) if config else {}
        label = id_to_label.get(label_id, id_to_label.get(str(label_id)))
        if not label or str(label).upper().startswith("LABEL_"):
            raise RuntimeError(
                "The classifier checkpoint has no usable id2label mapping. "
                "A fine-tuned M5 checkpoint with ClauseType labels is required."
            )
        return str(label)

    @staticmethod
    def _clause_type_for_label(label: str) -> ClauseType:
        normalized = label.strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return ClauseType(normalized)
        except ValueError as error:
            raise RuntimeError(
                f"Classifier label '{label}' is not one of the existing ClauseType values."
            ) from error

    @staticmethod
    def _contains_phrase(
        text: str,
        phrase: str,
    ) -> bool:
        """Check whether a normalized phrase exists in the text."""

        normalized_phrase = normalize_for_match(
            phrase
        )

        if not normalized_phrase:
            return False

        # Arabic phrases are matched by normalized substring.
        if any(
            "\u0600" <= char <= "\u06FF"
            for char in normalized_phrase
        ):
            return normalized_phrase in text

        # Latin phrases use word boundaries to reduce
        # substring false positives.
        escaped = re.escape(
            normalized_phrase
        )

        pattern = rf"(?<!\w){escaped}(?!\w)"

        return bool(
            re.search(
                pattern,
                text,
            )
        )

    @staticmethod
    def _keyword_weight(
        keyword: str,
    ) -> float:
        """
        Longer legal phrases receive slightly higher weight.
        """

        token_count = len(
            normalize_for_match(
                keyword
            ).split()
        )

        return 1.0 + 0.25 * max(
            0,
            token_count - 1,
        )

    def _classify_rules(
        self,
        text: str,
        title: str | None = None,
    ) -> Tuple[ClauseType, float, Dict]:

        original_text = text or ""
        original_title = title or ""

        normalized_text = normalize_for_match(
            original_text
        )

        normalized_title = normalize_for_match(
            original_title
        )

        if not normalized_text and not normalized_title:
            return (
                ClauseType.UNKNOWN,
                0.20,
                {
                    "method": "rule_assisted",
                    "scores": {},
                    "reason": "empty_text",
                },
            )

        token_count = max(
            1,
            len(
                normalized_text.split()
            ),
        )

        scores: Dict[ClauseType, float] = {}

        evidence: Dict[str, List[Dict]] = {}

        for clause_type, keywords in KEYWORDS.items():

            total_score = 0.0
            type_evidence: List[Dict] = []

            for keyword in keywords:

                normalized_keyword = normalize_for_match(
                    keyword
                )

                if not normalized_keyword:
                    continue

                body_hit = self._contains_phrase(
                    normalized_text,
                    normalized_keyword,
                )

                title_hit = (
                    bool(normalized_title)
                    and self._contains_phrase(
                        normalized_title,
                        normalized_keyword,
                    )
                )

                if not body_hit and not title_hit:
                    continue

                weight = self._keyword_weight(
                    normalized_keyword
                )

                if body_hit:
                    total_score += weight

                # A title match is stronger evidence.
                if title_hit:
                    total_score += weight * 1.5

                type_evidence.append(
                    {
                        "keyword": keyword,
                        "weight": round(
                            weight,
                            4,
                        ),
                        "body_match": body_hit,
                        "title_match": title_hit,
                    }
                )

            if total_score > 0:

                normalized_score = (
                    total_score
                    / (
                        1.0
                        + math.log1p(
                            token_count
                        )
                    )
                )

                scores[clause_type] = min(
                    0.99,
                    normalized_score,
                )

                evidence[
                    clause_type.value
                ] = type_evidence

        if not scores:
            return (
                ClauseType.UNKNOWN,
                0.20,
                {
                    "method": "rule_assisted",
                    "scores": {},
                    "evidence": {},
                    "reason": "no_keyword_match",
                },
            )

        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        best_type, best_raw_score = ranked[0]

        second_raw_score = (
            ranked[1][1]
            if len(ranked) > 1
            else 0.0
        )

        margin = max(
            0.0,
            best_raw_score - second_raw_score,
        )

        # Heuristic confidence.
        # This is NOT a probability.
        confidence = (
            0.45
            + min(
                0.40,
                best_raw_score * 0.20,
            )
            + min(
                0.10,
                margin * 0.10,
            )
        )

        confidence = max(
            0.20,
            min(
                0.95,
                confidence,
            ),
        )

        if best_raw_score < self.threshold:
            return (
                ClauseType.UNKNOWN,
                round(
                    confidence,
                    4,
                ),
                {
                    "method": "rule_assisted",
                    "scores": {
                        clause_type.value: round(
                            score,
                            4,
                        )
                        for clause_type, score in ranked
                    },
                    "evidence": evidence,
                    "best_candidate": best_type.value,
                    "margin": round(
                        margin,
                        4,
                    ),
                    "reason": "below_threshold",
                },
            )

        return (
            best_type,
            round(
                confidence,
                4,
            ),
            {
                "method": "rule_assisted",
                "scores": {
                    clause_type.value: round(
                        score,
                        4,
                    )
                    for clause_type, score in ranked
                },
                "evidence": evidence,
                "best_candidate": best_type.value,
                "margin": round(
                    margin,
                    4,
                ),
                "reason": "keyword_match",
            },
        )