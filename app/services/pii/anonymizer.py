from dataclasses import dataclass
from app.services.pii.detector import detect_pii, normalize_text
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# Exact placeholder mapping specified in Section 4
ENTITY_PLACEHOLDER_MAP: dict[str, str] = {
    "ACCOUNT_ID": "<ACCOUNT_ID>",
    "IBAN_CODE": "<IBAN>",
    "PHONE_NUMBER": "<PHONE>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "NATIONAL_ID": "<NATIONAL_ID>",
    "CARD_NUMBER": "<CARD_NUMBER>",
    "SWIFT_BIC": "<SWIFT_BIC>",
    "ROUTING_NUMBER": "<ROUTING_NUMBER>",
    "ADDRESS": "<ADDRESS>",
    "PAYMENT_HANDLE": "<PAYMENT_HANDLE>",
    "REFERENCE_ID": "<REFERENCE_ID>",
}


@dataclass
class ScrubResult:
  """Holds the scrubbed text and a safe count of replaced entity types (never raw values)."""

  scrubbed_text: str
  entity_counts: dict[str, int]
  total_redactions: int


def scrub_text(raw_text: str) -> ScrubResult:
  """Detects and replaces sensitive financial/personal PII with consistent placeholders

  while preserving names, merchant names, dates, amounts, and transaction descriptions.
  """
  normalized = normalize_text(raw_text)
  detected_entities = detect_pii(normalized)

  entity_counts: dict[str, int] = {}
  for item in detected_entities:
    placeholder = ENTITY_PLACEHOLDER_MAP.get(
        item.entity_type, f"<{item.entity_type}>"
    )
    entity_counts[placeholder] = entity_counts.get(placeholder, 0) + 1

  operators = {
      entity_type: OperatorConfig("replace", {"new_value": placeholder})
      for entity_type, placeholder in ENTITY_PLACEHOLDER_MAP.items()
  }

  anonymizer = AnonymizerEngine()
  anonymized = anonymizer.anonymize(
      text=normalized,
      analyzer_results=detected_entities,  # type: ignore[arg-type]
      operators=operators,
  )

  return ScrubResult(
      scrubbed_text=anonymized.text,
      entity_counts=entity_counts,
      total_redactions=len(detected_entities),
  )