from app.services.pii.detector import detect_pii
from app.services.pii.recognizers import is_valid_iban, is_valid_luhn


def test_iban_and_luhn_validators() -> None:
  assert is_valid_iban("PK36 SCBL 0000 0011 2345 6702") is True
  assert is_valid_iban("GB29 NWBK 6016 1331 9268 19") is True
  assert is_valid_iban("PK00 INVALID 1234") is False

  # Standard valid Luhn test card (Visa test number)
  assert is_valid_luhn("4532 0151 1283 0366") is True
  assert is_valid_luhn("4532 0151 1283 0367") is False


def test_detects_all_financial_and_personal_identifiers() -> None:
  sample = (
      "Account Holder: Hamza Tariq\n"
      "Account Number: 0123-4567890-01\n"
      "IBAN: PK36 SCBL 0000 0011 2345 6702\n"
      "Card: 4532 0151 1283 0366\n"
      "CNIC: 42101-1234567-1\n"
      "SSN: 123-45-6789\n"
      "SWIFT: SCBLPKKAXXX\n"
      "Routing Number: 021000021\n"
      "Sort Code: 20-45-67\n"
      "IFSC: SBIN0001234\n"
      "Phone: +92 300 1234567\n"
      "Email: hamza.tariq@example.com\n"
      "UPI ID: hamza@okaxis\n"
      "Address: House No 42, Street 10, Block F, North Nazimabad, Karachi\n"
      "2026-10-15 | Foodpanda | Ref: TXN-9988776655 | PKR 1,850.00\n"
  )
  results = detect_pii(sample)
  detected_types = {r.entity_type for r in results}

  assert "ACCOUNT_ID" in detected_types
  assert "IBAN_CODE" in detected_types
  assert "CARD_NUMBER" in detected_types
  assert "NATIONAL_ID" in detected_types
  assert "SWIFT_BIC" in detected_types
  assert "ROUTING_NUMBER" in detected_types
  assert "PHONE_NUMBER" in detected_types
  assert "EMAIL_ADDRESS" in detected_types
  assert "PAYMENT_HANDLE" in detected_types
  assert "ADDRESS" in detected_types
  assert "REFERENCE_ID" in detected_types