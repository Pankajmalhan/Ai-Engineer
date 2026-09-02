"""PII detection/redaction, offline heuristic + real NER-backed, behind the same
interface -- same Heuristic/real split as prior weeks' grader/refiner/rewriter.

RegexPIIRedactor is free, instant, and needs no model download, but is blind to
context-dependent entities (a name, a street address) that don't have a fixed shape.
PresidioPIIRedactor is Microsoft Presidio (built on spaCy NER) -- this replaces a
raw spaCy-NER-only pass with Presidio's purpose-built recognizer/anonymizer pipeline,
per this week's tooling update (see resources.md); it needs
`uv run python -m spacy download en_core_web_sm` once, but then runs fully offline
and catches PERSON entities regex fundamentally can't.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.config import PII_ENTITIES, PII_SPACY_MODEL
from app.models import PIIMatch

# --- Regex-only fallback --------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
_ID_RE = re.compile(r"\b(?:[A-Z]{2}-\d{6,9}|\d{3}-\d{2}-\d{4})\b")  # employee-ID- and SSN-shaped


class RegexPIIRedactor:
    def find(self, text: str) -> list[PIIMatch]:
        matches = []
        for pattern, entity_type in (
            (_ID_RE, "ID_NUMBER"),  # checked first: SSN-shaped strings would also match _PHONE_RE
            (_EMAIL_RE, "EMAIL_ADDRESS"),
            (_PHONE_RE, "PHONE_NUMBER"),
        ):
            for m in pattern.finditer(text):
                if any(m.start() < existing.end and m.end() > existing.start for existing in matches):
                    continue
                matches.append(PIIMatch(entity_type=entity_type, text=m.group(), start=m.start(), end=m.end()))
        return sorted(matches, key=lambda m: m.start)

    def redact(self, text: str) -> tuple[str, list[PIIMatch]]:
        matches = self.find(text)
        out, last = [], 0
        for m in matches:
            out.append(text[last : m.start])
            out.append(f"<{m.entity_type}>")
            last = m.end
        out.append(text[last:])
        return "".join(out), matches


# --- Presidio-backed NER redaction -----------------------------------------------------


@lru_cache(maxsize=1)
def _analyzer():
    from presidio_analyzer import Pattern, PatternRecognizer
    from presidio_analyzer.analyzer_engine import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": PII_SPACY_MODEL}],
        }
    )
    engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
    engine.registry.add_recognizer(
        PatternRecognizer(
            supported_entity="ID_NUMBER",
            patterns=[
                Pattern(name="employee_id", regex=r"\b[A-Z]{2}-\d{6,9}\b", score=0.85),
                Pattern(name="ssn_like", regex=r"\b\d{3}-\d{2}-\d{4}\b", score=0.85),
            ],
        )
    )
    return engine


def presidio_available() -> bool:
    try:
        _analyzer()
        return True
    except Exception:
        return False


class PresidioPIIRedactor:
    def __init__(self):
        from presidio_anonymizer import AnonymizerEngine

        self.analyzer = _analyzer()
        self.anonymizer = AnonymizerEngine()

    def find(self, text: str) -> list[PIIMatch]:
        results = self.analyzer.analyze(text=text, entities=PII_ENTITIES, language="en")
        return [
            PIIMatch(entity_type=r.entity_type, text=text[r.start : r.end], start=r.start, end=r.end)
            for r in results
        ]

    def redact(self, text: str) -> tuple[str, list[PIIMatch]]:
        results = self.analyzer.analyze(text=text, entities=PII_ENTITIES, language="en")
        if not results:
            return text, []
        anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
        matches = [
            PIIMatch(entity_type=r.entity_type, text=text[r.start : r.end], start=r.start, end=r.end)
            for r in results
        ]
        return anonymized.text, matches
