import re
import phonenumbers
from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


def is_valid_luhn(number_str: str) -> bool:
  """Validates a credit/debit card number using the Luhn checksum algorithm."""
  digits = [int(ch) for ch in number_str if ch.isdigit()]
  if len(digits) < 13 or len(digits) > 19:
    return False
  if len(set(digits)) == 1:
    return False
  checksum = 0
  parity = len(digits) % 2
  for idx, digit in enumerate(digits):
    if idx % 2 == parity:
      digit *= 2
      if digit > 9:
        digit -= 9
    checksum += digit
  return checksum % 10 == 0


def is_valid_iban(iban_str: str) -> bool:
  """Validates an international IBAN using ISO 13616 Modulo-97 arithmetic."""
  cleaned = re.sub(r"[\s\-]", "", iban_str).upper()
  if len(cleaned) < 15 or len(cleaned) > 34:
    return False
  if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$", cleaned):
    return False
  rearranged = cleaned[4:] + cleaned[:4]
  numeric_iban = "".join(
      str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged
  )
  try:
    return int(numeric_iban) % 97 == 1
  except ValueError:
    return False


class CustomIbanRecognizer(EntityRecognizer):
  """Detects spaced or unspaced IBANs on a single line with Mod-97 verification."""

  # Uses [ \t\-] instead of \s so IBAN matching never crosses a newline (\n)
  _IBAN_CANDIDATE_RE = re.compile(
      r"\b[A-Z]{2}\d{2}(?:[ \t\-]?[A-Z0-9]{4}){2,6}(?:[ \t\-]?[A-Z0-9]{1,4})?\b"
  )

  def __init__(self) -> None:
    super().__init__(
        supported_entities=["IBAN_CODE"],
        name="CustomIbanRecognizer",
        supported_language="en",
    )

  def load(self) -> None:
    pass

  def analyze(
      self,
      text: str,
      entities: list[str],
      nlp_artifacts: NlpArtifacts | None = None,
  ) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    if "IBAN_CODE" not in entities:
      return results
    for match in self._IBAN_CANDIDATE_RE.finditer(text):
      candidate = match.group(0)
      cleaned = re.sub(r"[ \t\-]", "", candidate)
      if is_valid_iban(candidate) or (
          16 <= len(cleaned) <= 34
          and cleaned[:2]
          in {"PK", "GB", "DE", "FR", "NL", "AE", "SA", "ES", "IT", "IE"}
      ):
        results.append(
            RecognizerResult(
                entity_type="IBAN_CODE",
                start=match.start(),
                end=match.end(),
                score=0.98 if is_valid_iban(candidate) else 0.88,
            )
        )
    return results


class CustomCardRecognizer(EntityRecognizer):
  """Detects 13-19 digit payment cards (including masked cards) and checks Luhn."""

  _CARD_RE = re.compile(r"\b(?:\d{4}[ \t\-]?){3}\d{1,7}\b|\b\d{13,19}\b")
  _MASKED_CARD_RE = re.compile(
      r"\b(?:\d{4}[ \t\-]?[X*]{4}[ \t\-]?[X*]{4}[ \t\-]?\d{4}|[X*]{4}[ \t\-]?[X*]{4}[ \t\-]?[X*]{4}[ \t\-]?\d{4})\b",
      re.IGNORECASE,
  )

  def __init__(self) -> None:
    super().__init__(
        supported_entities=["CARD_NUMBER"],
        name="CustomCardRecognizer",
        supported_language="en",
    )

  def load(self) -> None:
    pass

  def analyze(
      self,
      text: str,
      entities: list[str],
      nlp_artifacts: NlpArtifacts | None = None,
  ) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    if "CARD_NUMBER" not in entities:
      return results

    for match in self._CARD_RE.finditer(text):
      candidate = match.group(0)
      digits_only = "".join(ch for ch in candidate if ch.isdigit())
      if len(digits_only) < 13 or len(digits_only) > 19:
        continue
      prefix_window = text[max(0, match.start() - 35) : match.start()].lower()
      has_card_context = any(
          kw in prefix_window
          for kw in (
              "card",
              "visa",
              "mastercard",
              "amex",
              "debit",
              "credit",
              "pan",
              "pos",
          )
      )
      if is_valid_luhn(digits_only) or (
          has_card_context and len(digits_only) in {15, 16}
      ):
        results.append(
            RecognizerResult(
                entity_type="CARD_NUMBER",
                start=match.start(),
                end=match.end(),
                score=0.98 if is_valid_luhn(digits_only) else 0.88,
            )
        )

    for match in self._MASKED_CARD_RE.finditer(text):
      results.append(
          RecognizerResult(
              entity_type="CARD_NUMBER",
              start=match.start(),
              end=match.end(),
              score=0.95,
          )
      )
    return results


class InternationalPhoneRecognizer(EntityRecognizer):
  """Detects international and local phone numbers using phonenumbers + regex."""

  _LOCAL_PK_UK_US_RE = re.compile(
      r"(?:(?:\+|00)\d{1,3}[ \t\-]?)?(?:\(?\d{2,4}\)?[ \t\-]?)\d{3,4}[ \t\-]?\d{3,4}\b"
  )

  def __init__(self) -> None:
    super().__init__(
        supported_entities=["PHONE_NUMBER"],
        name="InternationalPhoneRecognizer",
        supported_language="en",
    )

  def load(self) -> None:
    pass

  def analyze(
      self,
      text: str,
      entities: list[str],
      nlp_artifacts: NlpArtifacts | None = None,
  ) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    if "PHONE_NUMBER" not in entities:
      return results

    seen_spans: set[tuple[int, int]] = set()
    for region in ("PK", "US", "GB", "CA", "AE", "IN"):
      for match in phonenumbers.PhoneNumberMatcher(text, region):
        span = (match.start, match.end)
        if span not in seen_spans:
          raw = text[match.start : match.end]
          if "." in raw or "/" in raw or "\n" in raw:
            continue
          seen_spans.add(span)
          results.append(
              RecognizerResult(
                  entity_type="PHONE_NUMBER",
                  start=match.start,
                  end=match.end,
                  score=0.92,
              )
          )

    for match in self._LOCAL_PK_UK_US_RE.finditer(text):
      span = (match.start(), match.end())
      if span in seen_spans:
        continue
      candidate = match.group(0).strip()
      digits = "".join(ch for ch in candidate if ch.isdigit())
      if len(digits) < 10 or len(digits) > 15:
        continue
      prefix_window = text[max(0, match.start() - 30) : match.start()].lower()
      has_phone_ctx = any(
          kw in prefix_window
          for kw in (
              "phone",
              "tel",
              "mobile",
              "cell",
              "contact",
              "call",
              "sms",
              "whatsapp",
          )
      )
      starts_intl_or_mobile = candidate.startswith(
          ("+92", "+44", "+1", "+971", "03")
      )
      if has_phone_ctx or starts_intl_or_mobile:
        results.append(
            RecognizerResult(
                entity_type="PHONE_NUMBER",
                start=match.start(),
                end=match.end(),
                score=0.90,
            )
        )
    return results


def build_custom_pattern_recognizers() -> list[PatternRecognizer]:
  """Builds regex + context recognizers for financial and personal identifiers."""
  recognizers: list[PatternRecognizer] = []

  # 1. National IDs: PK CNIC, US SSN, UK NINO
  recognizers.append(
      PatternRecognizer(
          supported_entity="NATIONAL_ID",
          name="NationalIdRecognizer",
          patterns=[
              Pattern("PK_CNIC_HYPHEN", r"\b\d{5}-\d{7}-\d\b", 0.98),
              Pattern(
                  "US_SSN",
                  r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",
                  0.96,
              ),
              Pattern(
                  "UK_NINO",
                  r"\b[A-CEGHJ-PR-TW-Z]{2}[ \t\-]?\d{2}[ \t\-]?\d{2}[ \t\-]?\d{2}[ \t\-]?[A-D]\b",
                  0.95,
              ),
          ],
          context=[
              "cnic",
              "ssn",
              "sin",
              "national",
              "insurance",
              "passport",
              "identity",
              "nadra",
          ],
      )
  )

  # 2. SWIFT / BIC Codes
  recognizers.append(
      PatternRecognizer(
          supported_entity="SWIFT_BIC",
          name="SwiftBicRecognizer",
          patterns=[
              Pattern(
                  "SWIFT_11_CHAR",
                  r"\b[A-Z]{4}(?:PK|GB|US|DE|FR|AE|IN|CA|AU|SG|NL|CH)[A-Z0-9]{2}(?:XXX|[A-Z0-9]{3})\b",
                  0.93,
              ),
          ],
          context=["swift", "bic", "intermediary", "correspondent", "wire"],
      )
  )

  # 3. Routing Numbers, UK Sort Codes, Indian IFSC, Canadian Transit Numbers
  recognizers.append(
      PatternRecognizer(
          supported_entity="ROUTING_NUMBER",
          name="RoutingAndSortCodeRecognizer",
          patterns=[
              Pattern("IN_IFSC", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", 0.96),
              Pattern("UK_SORT_CODE", r"\b\d{2}-\d{2}-\d{2}\b", 0.75),
              Pattern("CA_TRANSIT", r"\b\d{5}-\d{3}\b", 0.88),
              Pattern("US_ROUTING_9DIGIT", r"\b\d{9}\b", 0.45),
          ],
          context=[
              "routing",
              "aba",
              "sort",
              "sort code",
              "ifsc",
              "transit",
              "branch code",
              "bsb",
          ],
      )
  )

  # 4. Payment Handles, UPI IDs & Wallet IDs
  recognizers.append(
      PatternRecognizer(
          supported_entity="PAYMENT_HANDLE",
          name="PaymentHandleRecognizer",
          patterns=[
              Pattern(
                  "UPI_AND_WALLET_HANDLE",
                  r"\b[A-Za-z0-9._\-]{2,40}@(?:okaxis|okhdfcbank|oksbi|okicici|ybl|paytm|ibl|axl|apl|upi|nayapay|sadapay|easypaisa|jazzcash|raast|venmo|cashapp|zelle)\b",
                  0.98,
              ),
              Pattern(
                  "CASHTAG_HANDLE",
                  r"(?<!\w)\$[A-Za-z][A-Za-z0-9_]{2,20}\b",
                  0.92,
              ),
              Pattern(
                  "WALLET_ID_VALUE",
                  r"\b(?:WAL|WLT|UPI|PAYID)-\d[A-Z0-9\-]{4,24}\b",
                  0.95,
              ),
          ],
          context=[
              "upi",
              "wallet",
              "handle",
              "vpa",
              "cashtag",
              "venmo",
              "nayapay",
              "sadapay",
              "easypaisa",
              "jazzcash",
          ],
      )
  )

  # 5. Bank Account Numbers (Always numeric or masked digits)
  recognizers.append(
      PatternRecognizer(
          supported_entity="ACCOUNT_ID",
          name="BankAccountRecognizer",
          patterns=[
              Pattern(
                  "HYPHENATED_ACCT", r"\b\d{3,4}-\d{6,10}-\d{1,3}\b", 0.95
              ),
              Pattern(
                  "MASKED_ACCT", r"(?:[X*]{3,10}[ \t\-]?\d{3,6})\b", 0.92
              ),
              Pattern("NUMERIC_ACCT", r"\b\d{8,17}\b", 0.50),
          ],
          context=[
              "account",
              "acct",
              "a/c",
              "acc",
              "acc#",
              "acct#",
              "account no",
              "account number",
              "beneficiary account",
              "sender account",
          ],
      )
  )

  # 6. Transaction Reference, Trace & STAN Identifiers (Must contain digits!)
  recognizers.append(
      PatternRecognizer(
          supported_entity="REFERENCE_ID",
          name="TransactionReferenceRecognizer",
          patterns=[
              Pattern(
                  "PREFIXED_REF",
                  r"\b(?:REF|TXN|TRX|TRC|TRACE|STAN|RRN|UTR|FT|CHQ|AUTH|INV|PMT)[-#:\s]?(?=[A-Z0-9\-]{6,24}\b)(?=.*\d)[A-Z0-9\-]{6,24}\b",
                  0.96,
              ),
          ],
          context=[
              "ref",
              "reference",
              "trace",
              "txn",
              "trx",
              "utr",
              "rrn",
              "stan",
              "receipt",
              "auth",
          ],
      )
  )

  # 7. Physical / Customer Street Addresses (Single-line only using [ \t])
  recognizers.append(
      PatternRecognizer(
          supported_entity="ADDRESS",
          name="PhysicalAddressRecognizer",
          patterns=[
              Pattern(
                  "STREET_HOUSE_ADDRESS",
                  r"\b(?:House|Flat|Apt|Apartment|Plot|Suit|Suite)[ \t]*(?:No\.?|#)?[ \t]*\d+[A-Za-z0-9,/\- \t]{6,85}",
                  0.93,
              ),
          ],
          context=[
              "address",
              "street",
              "road",
              "avenue",
              "block",
              "sector",
              "postal",
              "zip",
              "residence",
          ],
      )
  )

  return recognizers