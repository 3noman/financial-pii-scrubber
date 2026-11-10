from functools import lru_cache
import re
import unicodedata
from app.services.pii.recognizers import (
    CustomCardRecognizer,
    CustomIbanRecognizer,
    InternationalPhoneRecognizer,
    build_custom_pattern_recognizers,
)
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

TARGET_PII_ENTITIES = [
    "IBAN_CODE",
    "CARD_NUMBER",
    "NATIONAL_ID",
    "ACCOUNT_ID",
    "ROUTING_NUMBER",
    "SWIFT_BIC",
    "PAYMENT_HANDLE",
    "REFERENCE_ID",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "ADDRESS",
]

PROTECTED_MERCHANTS = (
    "foodpanda",
    "netflix.com",
    "netflix",
    "tesco stores",
    "tesco",
    "amazon.com",
    "amazon.co.uk",
    "amazon",
    "uber",
    "spotify",
    "apple.com/bill",
    "google",
    "daraz",
    "careem",
    "steamgames.com",
)

_MONETARY_AMOUNT_RE = re.compile(
    r"(?:(?:PKR|USD|GBP|EUR|AED|CAD|INR|SAR|Rs\.?|\$|£|€)[ \t]*)?[+\-]?\d{1,3}(?:,\d{3})*\.\d{2}\b"
)
_DATE_RE = re.compile(
    r"\b(?:\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|\d{1,2}[ \t\-][A-Za-z]{3,9}[ \t\-]\d{2,4})\b"
)

# Direct contextual regexes using [ \t] (never matching across newlines) and requiring digits for numeric IDs
_DIRECT_CONTEXT_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    (
        "SWIFT_BIC",
        re.compile(
            r"\b(?:SWIFT|BIC|SWIFT/BIC|SWIFT Code|BIC Code)[ \t]*[:#\-][ \t]*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b",
            re.IGNORECASE,
        ),
        0.99,
    ),
    (
        "ROUTING_NUMBER",
        re.compile(
            r"\b(?:Routing(?:[ \t]+Number|[ \t]+No\.?)?|ABA|Sort Code|Transit(?:[ \t]+No\.?)?|IFSC)[ \t]*[:#\-][ \t]*(\d{2}-\d{2}-\d{2}|\d{5}-\d{3}|\d{9}|[A-Z]{4}0[A-Z0-9]{6})\b",
            re.IGNORECASE,
        ),
        0.99,
    ),
    (
        "ACCOUNT_ID",
        re.compile(
            r"\b(?:Account(?:[ \t]+Number|[ \t]+No\.?|[ \t]+ID|[ \t]*#)?|Acct(?:[ \t]+No\.?|[ \t]*#)?|A/C(?:[ \t]+No\.?|[ \t]*#)?)[ \t]*[:#\-][ \t]*(?=[A-Z0-9\-]{6,22}\b)(?=[A-Z0-9\-]*\d)([A-Z0-9][A-Z0-9\-]{5,21})\b",
            re.IGNORECASE,
        ),
        0.98,
    ),
    (
        "REFERENCE_ID",
        re.compile(
            r"\b(?:Ref(?:erence)?(?:[ \t]+ID|[ \t]+No\.?|[ \t]*#)?|Trace(?:[ \t]+ID|[ \t]+No\.?|[ \t]*#)?|TXN(?:[ \t]+ID|[ \t]*#)?|UTR|RRN|STAN)[ \t]*[:#\-][ \t]*(?=[A-Z0-9\-]{6,26}\b)(?=[A-Z0-9\-]*\d)([A-Z0-9][A-Z0-9\-]{5,25})\b",
            re.IGNORECASE,
        ),
        0.98,
    ),
    (
        "NATIONAL_ID",
        re.compile(
            r"\b(?:CNIC|SSN|SIN|National ID|NINO|Passport(?:[ \t]+No\.?)?)[ \t]*[:#\-][ \t]*(?=[A-Z0-9\-]{6,20}\b)(?=[A-Z0-9\-]*\d)([A-Z0-9][A-Z0-9\-]{5,19})\b",
            re.IGNORECASE,
        ),
        0.99,
    ),
    (
        "PAYMENT_HANDLE",
        re.compile(
            r"\b(?:UPI(?:[ \t]+ID)?|Payment Handle|Wallet(?:[ \t]+ID)?|VPA|Raast ID)[ \t]*[:#\-][ \t]*([A-Za-z0-9._\-$@]{4,45})\b",
            re.IGNORECASE,
        ),
        0.98,
    ),
    (
        "ADDRESS",
        re.compile(
            r"\b(?:Address|Billing Address|Customer Address|Home Address|Mailing Address)[ \t]*[:\-][ \t]*([^\n\r|]{8,100})",
            re.IGNORECASE,
        ),
        0.98,
    ),
]


def normalize_text(text: str) -> str:
    """Applies NFKC Unicode normalization while preserving line structure."""
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.replace("\u00a0", " ")


@lru_cache(maxsize=1)
def get_analyzer_engine() -> AnalyzerEngine:
    """Initializes and caches the Presidio AnalyzerEngine with spaCy + custom recognizers."""
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()

    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    analyzer.registry.add_recognizer(CustomIbanRecognizer())
    analyzer.registry.add_recognizer(CustomCardRecognizer())
    analyzer.registry.add_recognizer(InternationalPhoneRecognizer())
    for rec in build_custom_pattern_recognizers():
        analyzer.registry.add_recognizer(rec)

    return analyzer


def _is_protected_span(text: str, start: int, end: int, entity_type: str) -> bool:
    """Returns True if the detected span is a merchant name, date, pure word, or currency amount."""
    snippet = text[start:end].strip()
    snippet_lower = snippet.lower()

    # 1. Never redact across newlines
    if "\n" in snippet or "\r" in snippet:
        return True

    # 2. Never redact protected merchant domains or names
    for merchant in PROTECTED_MERCHANTS:
        if snippet_lower == merchant or merchant in snippet_lower:
            if entity_type not in {"IBAN_CODE", "CARD_NUMBER", "NATIONAL_ID"}:
                return True

    # 3. Account IDs, Reference IDs, Card Numbers, National IDs, and Routing Numbers MUST contain at least one digit
    if entity_type in {
        "ACCOUNT_ID",
        "REFERENCE_ID",
        "CARD_NUMBER",
        "NATIONAL_ID",
        "ROUTING_NUMBER",
        "IBAN_CODE",
    }:
        if not any(ch.isdigit() for ch in snippet):
            return True

    # 4. Never redact decimal monetary amounts
    if re.fullmatch(r"[+\-]?\d{1,3}(?:,\d{3})*\.\d{2}", snippet):
        return True
    for m in _MONETARY_AMOUNT_RE.finditer(text):
        if start >= m.start() and end <= m.end():
            return True

    # 5. Never redact standard transaction dates
    for d in _DATE_RE.finditer(text):
        if start >= d.start() and end <= d.end():
            return True

    # 6. If EMAIL_ADDRESS matched a UPI/Wallet handle, let PAYMENT_HANDLE take precedence
    if entity_type == "EMAIL_ADDRESS" and re.search(
        r"@(?:okaxis|okhdfcbank|oksbi|okicici|ybl|paytm|ibl|axl|apl|upi|nayapay|sadapay|easypaisa|jazzcash|raast|venmo|cashapp|zelle)\b",
        snippet_lower,
    ):
        return True

    return False


def _resolve_overlaps(
    results: list[RecognizerResult],
) -> list[RecognizerResult]:
    """Resolves overlapping entity spans by preferring higher confidence and longer spans."""
    if not results:
        return []

    priority_rank = {
        "IBAN_CODE": 10,
        "CARD_NUMBER": 9,
        "NATIONAL_ID": 9,
        "PAYMENT_HANDLE": 8,
        "SWIFT_BIC": 8,
        "ROUTING_NUMBER": 7,
        "ACCOUNT_ID": 7,
        "REFERENCE_ID": 6,
        "EMAIL_ADDRESS": 6,
        "PHONE_NUMBER": 5,
        "ADDRESS": 5,
    }

    sorted_results = sorted(
        results,
        key=lambda r: (
            r.start,
            -(r.end - r.start),
            -priority_rank.get(r.entity_type, 1),
            -r.score,
        ),
    )

    resolved: list[RecognizerResult] = []
    for candidate in sorted_results:
        overlap_found = False
        for idx, existing in enumerate(resolved):
            if candidate.start < existing.end and candidate.end > existing.start:
                overlap_found = True
                cand_len = candidate.end - candidate.start
                exist_len = existing.end - existing.start
                cand_prio = priority_rank.get(candidate.entity_type, 1)
                exist_prio = priority_rank.get(existing.entity_type, 1)
                if (
                    cand_len > exist_len and candidate.score >= existing.score - 0.1
                ) or (cand_prio > exist_prio and cand_len >= exist_len):
                    resolved[idx] = candidate
                break
        if not overlap_found:
            resolved.append(candidate)

    return sorted(resolved, key=lambda r: r.start)


def detect_pii(text: str, score_threshold: float = 0.60) -> list[RecognizerResult]:
    """Detects financial and personal PII entities while preserving names, merchants, dates, and amounts."""
    normalized = normalize_text(text)
    analyzer = get_analyzer_engine()

    presidio_results = analyzer.analyze(
        text=normalized,
        language="en",
        entities=TARGET_PII_ENTITIES,
        score_threshold=score_threshold,
    )

    combined_results: list[RecognizerResult] = list(presidio_results)

    for entity_type, pattern, score in _DIRECT_CONTEXT_PATTERNS:
        for match in pattern.finditer(normalized):
            group_idx = 1 if match.lastindex else 0
            start, end = match.span(group_idx)
            combined_results.append(
                RecognizerResult(
                    entity_type=entity_type,
                    start=start,
                    end=end,
                    score=score,
                )
            )

    filtered_results = [
        res
        for res in combined_results
        if not _is_protected_span(normalized, res.start, res.end, res.entity_type)
    ]

    return _resolve_overlaps(filtered_results)
