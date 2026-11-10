from pathlib import Path
from docx import Document

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 1. Standard Bank Statement (TXT)
TXT_STATEMENT = """STANDARD CHARTERED BANK - ACCOUNT STATEMENT
Account Holder: Sarah Ahmed
Account Number: 0192-8877665-01
IBAN: PK36 SCBL 0000 0011 2345 6702
CNIC: 42101-7654321-9
Phone: +92 321 9876543
Email: sarah.ahmed@example.com
Address: House No 14, Street 5, Phase 6, DHA, Karachi
Currency: PKR

TRANSACTIONS FOR OCTOBER 2026:
2026-10-01 | Tech Innovations Inc | Monthly Salary Deposit | Credit | PKR 185,000.00 | Bal: PKR 210,000.00
2026-10-02 | K-Electric | Electricity Bill Payment | Debit | PKR 14,500.00 | Bal: PKR 195,500.00
2026-10-03 | Foodpanda | Dinner Delivery Order | Ref: TXN-11223344 | Debit | PKR 2,450.00 | Bal: PKR 193,050.00
2026-10-05 | Imtiaz Super Market | Monthly Groceries | Debit | PKR 18,200.00 | Bal: PKR 174,850.00
2026-10-07 | Foodpanda | Lunch Order | Ref: TXN-55667788 | Debit | PKR 1,650.00 | Bal: PKR 173,200.00
2026-10-10 | Shell Fuel Station | Fuel refill | Debit | PKR 6,500.00 | Bal: PKR 166,700.00
2026-10-12 | Netflix.com | Monthly Subscription | Debit | PKR 1,100.00 | Bal: PKR 165,600.00
2026-10-15 | Spotify | Family Premium Plan | Debit | PKR 599.00 | Bal: PKR 165,001.00
2026-10-18 | Daraz.pk | Electronics & Accessories | Debit | PKR 8,900.00 | Bal: PKR 156,101.00
2026-10-22 | Uber | Ride to Airport | Debit | PKR 1,450.00 | Bal: PKR 154,651.00
"""

# 2. Digital Wallet Transactions (CSV)
CSV_STATEMENT = """Date,Merchant,Description,Type,Amount,Currency,Contact,Wallet_ID
2026-10-04,Foodpanda,Food Delivery,Debit,1850.00,PKR,sarah@nayapay,WAL-4829104
2026-10-06,Uber,Ride home,Debit,950.00,PKR,sarah@nayapay,WAL-4829104
2026-10-11,Apple.com/bill,iCloud 200GB Storage,Debit,600.00,PKR,sarah@nayapay,WAL-4829104
2026-10-16,Foodpanda,Late Night Snack,Debit,1200.00,PKR,sarah@nayapay,WAL-4829104
2026-10-20,Careem,City Delivery,Debit,450.00,PKR,sarah@nayapay,WAL-4829104
2026-10-25,Freelance Client,Consulting Remittance,Credit,35000.00,PKR,sarah@nayapay,WAL-4829104
"""


def generate() -> None:
  (DATA_DIR / "bank_statement_october.txt").write_text(
      TXT_STATEMENT, encoding="utf-8"
  )
  (DATA_DIR / "nayapay_wallet.csv").write_text(CSV_STATEMENT, encoding="utf-8")

  # 3. UK Bank Statement in Word Table (DOCX)
  doc = Document()
  doc.add_heading("Barclays Bank UK - Current Account Statement", 0)
  doc.add_paragraph("Account Holder: Sarah Ahmed")
  doc.add_paragraph("Sort Code: 20-45-67 | Account No: 88776655")
  doc.add_paragraph("IBAN: GB29 NWBK 6016 1331 9268 19 | SWIFT: BARCGB22XXX")
  doc.add_paragraph(
      "Customer Address: 42 Victoria Street, Flat 3B, London SW1E 5ND"
  )
  doc.add_paragraph("Currency: GBP")

  table = doc.add_table(rows=1, cols=5)
  headers = ["Date", "Merchant", "Description", "Type", "Amount"]
  for idx, h in enumerate(headers):
    table.rows[0].cells[idx].text = h

  rows_data = [
      ("2026-10-02", "TESCO STORES", "Groceries", "Debit", "GBP 42.50"),
      (
          "2026-10-05",
          "Netflix.com",
          "UK Subscription",
          "Debit",
          "GBP 10.99",
      ),
      ("2026-10-09", "Amazon.co.uk", "Books & Stationery", "Debit", "GBP 28.40"),
      ("2026-10-14", "Transport for London", "Tube travel", "Debit", "GBP 7.60"),
  ]
  for r in rows_data:
    row = table.add_row()
    for col_idx, val in enumerate(r):
      row.cells[col_idx].text = val

  doc.save(str(DATA_DIR / "uk_barclays_statement.docx"))
  print(
      "SUCCESS: Generated 3 multi-format test statements in 'data/' directory!"
  )


if __name__ == "__main__":
  generate()