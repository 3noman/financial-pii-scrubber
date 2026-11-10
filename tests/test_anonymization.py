from app.services.pii.anonymizer import scrub_text


def test_scrubs_identifiers_with_exact_placeholders_and_preserves_context() -> None:
  raw_statement = (
      "Statement for Account Holder: Sarah Ahmed\n"
      "Account No: 0192-8877665-01 | IBAN: PK36 SCBL 0000 0011 2345 6702\n"
      "CNIC: 42101-7654321-9 | Phone: +92 321 9876543 | Email: sarah.ahmed@gmail.com\n"
      "Card: 4532 0151 1283 0366 | SWIFT: SCBLPKKAXXX | Routing Number: 021000021\n"
      "Address: House No 14, Street 5, Phase 6, DHA, Karachi\n"
      "Payment Handle: sarah@nayapay\n"
      "Transactions:\n"
      "2026-10-01 | Foodpanda | Order Dinner | Ref: TXN-1122334455 | Debit | PKR 2,450.00 | Bal: PKR 85,000.00\n"
      "2026-10-03 | Netflix.com | Monthly Subscription | Debit | USD 15.99\n"
      "2026-10-05 | TESCO STORES | Groceries | Debit | GBP 42.30\n"
      "2026-10-08 | Amazon | Electronics | Debit | USD 89.99\n"
      "2026-10-10 | Uber | Ride to Airport | Debit | PKR 1,200.00\n"
      "2026-10-12 | Spotify | Family Plan | Debit | PKR 599.00\n"
  )

  result = scrub_text(raw_statement)
  scrubbed = result.scrubbed_text

  # 1. Verify all sensitive values are completely removed
  assert "0192-8877665-01" not in scrubbed
  assert "PK36 SCBL 0000 0011 2345 6702" not in scrubbed
  assert "42101-7654321-9" not in scrubbed
  assert "321 9876543" not in scrubbed
  assert "sarah.ahmed@gmail.com" not in scrubbed
  assert "4532 0151 1283 0366" not in scrubbed
  assert "SCBLPKKAXXX" not in scrubbed
  assert "021000021" not in scrubbed
  assert "House No 14, Street 5" not in scrubbed
  assert "sarah@nayapay" not in scrubbed
  assert "TXN-1122334455" not in scrubbed

  # 2. Verify required placeholders are present
  for expected_placeholder in (
      "<ACCOUNT_ID>",
      "<IBAN>",
      "<NATIONAL_ID>",
      "<PHONE>",
      "<EMAIL>",
      "<CARD_NUMBER>",
      "<SWIFT_BIC>",
      "<ROUTING_NUMBER>",
      "<ADDRESS>",
      "<PAYMENT_HANDLE>",
      "<REFERENCE_ID>",
  ):
    assert expected_placeholder in scrubbed

  # 3. Verify preserved names, merchants, dates, amounts, balances, and descriptions
  for preserved_item in (
      "Sarah Ahmed",
      "Foodpanda",
      "Netflix.com",
      "TESCO STORES",
      "Amazon",
      "Uber",
      "Spotify",
      "2026-10-01",
      "PKR 2,450.00",
      "PKR 85,000.00",
      "USD 15.99",
      "GBP 42.30",
      "Monthly Subscription",
  ):
    assert preserved_item in scrubbed