from dataclasses import dataclass, field
import re
from app.services.pii.anonymizer import ENTITY_PLACEHOLDER_MAP
from app.services.pii.detector import detect_pii
from app.services.pii.recognizers import is_valid_iban, is_valid_luhn

ALLOWED_PLACEHOLDERS = set(ENTITY_PLACEHOLDER_MAP.values())

# Independent strict audit patterns to catch anything that slipped past the first pass
_RESIDUAL_CNIC_RE = re.compile(r"\b\d{5}-\d{7}-\d\b")
_RESIDUAL_SSN_RE = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"
)
_RESIDUAL_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_RESIDUAL_IBAN_CANDIDATE_RE = re.compile(
    r"\b[A-Z]{2}\d{2}(?:[ \t\-]?[A-Z0-9]{4}){2,6}(?:[ \t\-]?[A-Z0-9]{1,4})?\b"
)
_RESIDUAL_CARD_CANDIDATE_RE = re.compile(
    r"\b(?:\d{4}[ \t\-]?){3}\d{1,7}\b|\b\d{13,19}\b"
)
_PLACEHOLDER_TOKEN_RE = re.compile(r"<[A-Z_]+>")


@dataclass
class VerificationReport:
  """Result of the independent post-scrubbing security gate.

  Never stores raw sensitive values—only safe category descriptions.
  """

  passed: bool
  findings: list[str] = field(default_factory=list)
  placeholders_verified: bool = True


def verify_scrubbed_text(scrubbed_text: str) -> VerificationReport:
  """Independently inspects scrubbed output for any remaining sensitive identifiers

  or malformed placeholders before PostgreSQL storage or Groq API transmission.
  """
  findings: list[str] = []

  if not scrubbed_text or not scrubbed_text.strip():
    return VerificationReport(
        passed=False,
        findings=["Scrubbed text is empty."],
        placeholders_verified=False,
    )

  # 1. Verify placeholder consistency (ensure any <TAG> is an approved placeholder)
  placeholders_ok = True
  for match in _PLACEHOLDER_TOKEN_RE.finditer(scrubbed_text):
    token = match.group(0)
    if token not in ALLOWED_PLACEHOLDERS:
      placeholders_ok = False
      findings.append(f"Unrecognized placeholder token format: {token}")

  # Strip valid placeholders before scanning for residual PII
  text_without_placeholders = scrubbed_text
  for ph in ALLOWED_PLACEHOLDERS:
    text_without_placeholders = text_without_placeholders.replace(ph, " ")

  # 2. Independent Check 1: Re-run detector on placeholder-stripped text
  residual_entities = detect_pii(
      text_without_placeholders, score_threshold=0.65
  )
  for ent in residual_entities:
    msg = f"Residual {ent.entity_type} detected during verification re-scan."
    if msg not in findings:
      findings.append(msg)

  # 3. Independent Check 2: Strict regex + checksum audit for high-risk identifiers
  if _RESIDUAL_CNIC_RE.search(text_without_placeholders):
    msg = "Residual National ID (CNIC pattern) detected."
    if msg not in findings:
      findings.append(msg)

  if _RESIDUAL_SSN_RE.search(text_without_placeholders):
    msg = "Residual National ID (SSN pattern) detected."
    if msg not in findings:
      findings.append(msg)

  if _RESIDUAL_EMAIL_RE.search(text_without_placeholders):
    msg = "Residual Email Address detected."
    if msg not in findings:
      findings.append(msg)

  for iban_match in _RESIDUAL_IBAN_CANDIDATE_RE.finditer(
      text_without_placeholders
  ):
    if is_valid_iban(iban_match.group(0)):
      msg = "Residual valid IBAN checksum detected."
      if msg not in findings:
        findings.append(msg)

  for card_match in _RESIDUAL_CARD_CANDIDATE_RE.finditer(
      text_without_placeholders
  ):
    digits = "".join(ch for ch in card_match.group(0) if ch.isdigit())
    if 13 <= len(digits) <= 19 and is_valid_luhn(digits):
      msg = "Residual Luhn-valid Card Number detected."
      if msg not in findings:
        findings.append(msg)

  passed = len(findings) == 0 and placeholders_ok
  return VerificationReport(
      passed=passed,
      findings=findings,
      placeholders_verified=placeholders_ok,
  )