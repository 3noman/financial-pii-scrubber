from decimal import Decimal, InvalidOperation
import re
from app.schemas.schemas import TransactionSchema

MONTH_MAP = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

# 1. Full date with year: 2026-10-05, 05/10/2026, 12-Nov-2026, Dec 30, 2022
_FULL_DATE_RE = re.compile(
    r"\b("
    r"\d{4}[-/]\d{2}[-/]\d{2}"
    r"|\d{2}[-/]\d{2}[-/]\d{2,4}"
    r"|\d{1,2}[\s\-][A-Za-z]{3,9}[\s\-,]*\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
    r")\b"
)

# 2. Short Month-Day date at the start of a transaction row: "Dec 30", "15 Oct", "05/12"
_SHORT_DATE_START_RE = re.compile(
    r"^(?P<short_date>"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
    r"|\d{2}/\d{2}"
    r")\b",
    re.IGNORECASE,
)

# Matches currency + decimal amount, e.g. "PKR 2,450.00", "USD 15.99", "$33,781.82", "4.00"
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?P<curr>PKR|USD|GBP|EUR|AED|CAD|INR|SAR|Rs\.?|\$|£|€)?[ \t]*(?P<sign>[+\-])?[ \t]*(?P<val>\d{1,3}(?:,\d{3})*\.\d{2})\b"
)

# Lines that are summary headers/footers rather than individual transactions
_SUMMARY_SKIP_RE = re.compile(
    r"\b(?:opening\s+balance|closing\s+balance|balance\s+forward|brought\s+forward|"
    r"account\s+summary|total\s+withdrawals|total\s+deposits|page\s+\d+\s+of\s+\d+)\b",
    re.IGNORECASE,
)

_CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
    "RS": "PKR",
    "RS.": "PKR",
}

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Food & Dining": (
        "foodpanda",
        "restaurant",
        "cafe",
        "coffee",
        "kfc",
        "mcdonald",
        "pizza",
        "dinner",
        "lunch",
        "burger",
        "deliveroo",
        "uber eats",
        "doordash",
        "starbucks",
        "tim hortons",
    ),
    "Groceries": (
        "tesco",
        "carrefour",
        "imtiaz",
        "naheed",
        "metro",
        "grocery",
        "groceries",
        "supermarket",
        "walmart",
        "sainsbury",
        "aldi",
        "mart",
        "costco",
        "loblaws",
    ),
    "Subscriptions": (
        "netflix",
        "spotify",
        "apple.com/bill",
        "youtube",
        "prime video",
        "chatgpt",
        "openai",
        "icloud",
        "subscription",
        "adobe",
        "microsoft",
    ),
    "Transport & Travel": (
        "uber",
        "careem",
        "indrive",
        "shell",
        "pso",
        "total parco",
        "fuel",
        "petrol",
        "airline",
        "airways",
        "ride",
        "taxi",
        "parking",
        "train",
        "transport",
    ),
    "Shopping & E-Commerce": (
        "amazon",
        "daraz",
        "ebay",
        "zara",
        "nike",
        "electronics",
        "clothing",
        "mall",
        "shopify",
        "ikea",
    ),
    "Utilities & Bank Fees": (
        "electric",
        "k-electric",
        "lesco",
        "ssgc",
        "sngpl",
        "ptcl",
        "nayatel",
        "stormfiber",
        "water",
        "gas",
        "internet",
        "utility",
        "mobile bill",
        "jazz",
        "zong",
        "telenor",
        "account fee",
        "stmnt fee",
        "statement fee",
        "service charge",
        "bank fee",
        "fee",
    ),
    "Income & Deposits": (
        "salary",
        "payroll",
        "dividend",
        "freelance",
        "refund",
        "waiver",
        "fee waiver",
        "interest credit",
        "deposit",
        "inward transfer",
    ),
    "Transfers & Wallet": (
        "transfer",
        "raast",
        "ibft",
        "atm withdrawal",
        "atm",
        "wallet",
        "topup",
        "e-transfer",
        "interac",
    ),
}


def categorize_transaction(
    merchant: str, description: str, tx_type: str
) -> str:
  """Assigns an estimated spending category using deterministic keyword rules."""
  combined = f"{merchant} {description}".lower()
  if tx_type == "Credit" and any(
      kw in combined for kw in CATEGORY_KEYWORDS["Income & Deposits"]
  ):
    return "Income & Deposits"
  for category, keywords in CATEGORY_KEYWORDS.items():
    if any(kw in combined for kw in keywords):
      return category
  return "Income & Deposits" if tx_type == "Credit" else "General Expenses"


def _normalize_currency(raw_curr: str | None, default_curr: str = "PKR") -> str:
  if not raw_curr:
    return default_curr
  cleaned = raw_curr.strip().upper()
  return _CURRENCY_SYMBOL_MAP.get(cleaned, cleaned)


def _normalize_short_date(short_date_str: str, default_year: str) -> str:
  """Converts 'Dec 30' or '30 Dec' + default_year '2022' into '2022-12-30'."""
  cleaned = short_date_str.replace(".", "").replace(",", "").strip()
  parts = cleaned.split()
  if len(parts) == 2:
    p0, p1 = parts[0].lower(), parts[1].lower()
    if p0 in MONTH_MAP and p1.isdigit():
      return f"{default_year}-{MONTH_MAP[p0]}-{int(p1):02d}"
    if p1 in MONTH_MAP and p0.isdigit():
      return f"{default_year}-{MONTH_MAP[p1]}-{int(p0):02d}"
  return f"{default_year}-{cleaned}"


def parse_transactions_from_scrubbed_text(
    scrubbed_text: str,
) -> list[TransactionSchema]:
  """Extracts structured TransactionSchema items from verified scrubbed statement text.

  Supports: - Pipe-delimited rows (CSV/DOCX/PDF tables) - Full dates
  (YYYY-MM-DD, DD/MM/YYYY) and short statement dates (Dec 30, 15 Oct) -
  Multi-row transactions sharing the previous line's date (like CIBC/Chase PDF
  statements) - Automatic Debit/Credit inference from running balance changes
  """
  transactions: list[TransactionSchema] = []
  detected_default_currency = "PKR"

  # Detect dominant currency code or symbol in statement
  curr_match = re.search(
      r"\b(PKR|USD|GBP|EUR|AED|CAD|INR|SAR)\b", scrubbed_text
  )
  if curr_match:
    detected_default_currency = curr_match.group(1)
  elif "$" in scrubbed_text:
    detected_default_currency = (
        "CAD" if "cibc" in scrubbed_text.lower() else "USD"
    )
  elif "£" in scrubbed_text:
    detected_default_currency = "GBP"
  elif "€" in scrubbed_text:
    detected_default_currency = "EUR"

  # Detect statement year from header (e.g. "For Dec 1 to Dec 31, 2022")
  year_match = re.search(r"\b(20\d{2})\b", scrubbed_text)
  statement_year = year_match.group(1) if year_match else "2026"

  in_transaction_table = False
  last_seen_date: str | None = None
  previous_balance: Decimal | None = None

  for raw_line in scrubbed_text.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("---- File:"):
      in_transaction_table = False
      last_seen_date = None
      previous_balance = None
      continue

    line_lower = line.lower()

    # Track Opening Balance so we can infer Withdrawal vs Deposit from balance changes
    if "opening balance" in line_lower:
      ob_matches = list(_CURRENCY_AMOUNT_RE.finditer(line))
      if ob_matches:
        try:
          previous_balance = Decimal(ob_matches[-1].group("val").replace(",", ""))
        except InvalidOperation:
          pass
      in_transaction_table = True
      continue

    if "transaction details" in line_lower or (
        "date" in line_lower
        and "description" in line_lower
        and ("amount" in line_lower or "withdrawals" in line_lower or "debit" in line_lower)
    ):
      in_transaction_table = True
      continue

    if "closing balance" in line_lower:
      in_transaction_table = False
      continue

    if _SUMMARY_SKIP_RE.search(line):
      continue

    amount_matches = list(_CURRENCY_AMOUNT_RE.finditer(line))
    if not amount_matches:
      continue

    # 1. Check for full date (e.g. 2026-10-03) or short date (e.g. Dec 30)
    full_date_match = _FULL_DATE_RE.search(line)
    short_date_match = _SHORT_DATE_START_RE.match(line)

    tx_date: str | None = None
    date_end_idx = 0

    if full_date_match:
      tx_date = full_date_match.group(1).strip()
      date_end_idx = full_date_match.end()
      last_seen_date = tx_date
    elif short_date_match:
      tx_date = _normalize_short_date(
          short_date_match.group("short_date"), statement_year
      )
      date_end_idx = short_date_match.end()
      last_seen_date = tx_date
    elif (
        in_transaction_table
        and last_seen_date is not None
        and len(amount_matches) >= 2
    ):
      # Continuation transaction row on the same date (e.g. CIBC "BALANCE FEE WAIVER 4.00 33,781.82")
      tx_date = last_seen_date
      date_end_idx = 0
    else:
      continue

    # 2. Extract primary amount and optional running balance
    primary_match = amount_matches[0]
    balance_val: Decimal | None = None

    if len(amount_matches) >= 2:
      last_match = amount_matches[-1]
      try:
        balance_val = Decimal(last_match.group("val").replace(",", ""))
      except InvalidOperation:
        balance_val = None

    try:
      raw_amount_str = primary_match.group("val").replace(",", "")
      amount_val = Decimal(raw_amount_str)
    except InvalidOperation:
      continue

    if amount_val <= Decimal("0.00"):
      continue

    currency = _normalize_currency(
        primary_match.group("curr"), detected_default_currency
    )

    # 3. Determine Debit vs Credit (using explicit keywords, +/- sign, or running balance delta!)
    sign_str = primary_match.group("sign") or ""
    if "debit" in line_lower or sign_str == "-":
      tx_type = "Debit"
    elif (
        "credit" in line_lower
        or "salary" in line_lower
        or "deposit" in line_lower
        or "payroll" in line_lower
        or "waiver" in line_lower
        or "refund" in line_lower
        or sign_str == "+"
    ):
      tx_type = "Credit"
    elif previous_balance is not None and balance_val is not None:
      # Infer from running balance change!
      if balance_val > previous_balance:
        tx_type = "Credit"
      else:
        tx_type = "Debit"
    else:
      tx_type = "Debit"

    if balance_val is not None:
      previous_balance = balance_val

    # 4. Extract Merchant and Description
    if "|" in line:
      parts = [p.strip() for p in line.split("|") if p.strip()]
      non_meta_parts: list[str] = []
      for p in parts:
        if full_date_match and p == full_date_match.group(1).strip():
          continue
        if p.lower() in {"debit", "credit", "dr", "cr"}:
          continue
        if p.lower().startswith(("bal:", "balance:")):
          continue
        if _CURRENCY_AMOUNT_RE.fullmatch(p):
          continue
        non_meta_parts.append(p)

      merchant_name = non_meta_parts[0] if non_meta_parts else "Merchant"
      description = (
          " | ".join(non_meta_parts[1:])
          if len(non_meta_parts) > 1
          else merchant_name
      )
    else:
      cleaned_desc = line[date_end_idx : primary_match.start()].strip(" -|:\t")
      if not cleaned_desc:
        cleaned_desc = "Statement Transaction"
      tokens = cleaned_desc.split()
      merchant_name = " ".join(tokens[:3]) if len(tokens) >= 3 else cleaned_desc
      description = cleaned_desc

    merchant_name = re.sub(
        r"\bRef\s*:\s*<[A-Z_]+>", "", merchant_name, flags=re.IGNORECASE
    ).strip(" -|")
    if not merchant_name:
      merchant_name = "General Merchant"

    category = categorize_transaction(merchant_name, description, tx_type)

    transactions.append(
        TransactionSchema(
            transaction_date=tx_date,
            merchant_name=merchant_name[:250],
            description=description[:500],
            transaction_type=tx_type,
            amount=amount_val,
            currency=currency,
            balance=balance_val,
            category=category,
        )
    )

  return transactions