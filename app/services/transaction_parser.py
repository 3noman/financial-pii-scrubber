from decimal import Decimal, InvalidOperation
import re
from app.schemas.schemas import TransactionSchema

# Matches dates at the start or inside a transaction line (YYYY-MM-DD, DD/MM/YYYY, DD-MMM-YYYY)
_LINE_DATE_RE = re.compile(
    r"\b(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|\d{1,2}[\s\-][A-Za-z]{3,9}[\s\-]\d{2,4})\b"
)

# Matches currency + decimal amount, e.g. "PKR 2,450.00", "USD 15.99", "£42.50", "-1,200.00"
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?P<curr>PKR|USD|GBP|EUR|AED|CAD|INR|SAR|Rs\.?|\$|£|€)?\s*(?P<sign>[+\-])?\s*(?P<val>\d{1,3}(?:,\d{3})*\.\d{2})\b"
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
    "Utilities & Bills": (
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
    ),
    "Income & Deposits": (
        "salary",
        "payroll",
        "dividend",
        "freelance",
        "refund",
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


def parse_transactions_from_scrubbed_text(
    scrubbed_text: str,
) -> list[TransactionSchema]:
  """Extracts structured TransactionSchema items from verified scrubbed statement text.

  Supports pipe-delimited rows (from CSV/DOCX/PDF tables) and free-text banking
  lines.
  """
  transactions: list[TransactionSchema] = []
  detected_default_currency = "PKR"

  # Detect dominant currency in statement header if present
  curr_match = re.search(
      r"\b(PKR|USD|GBP|EUR|AED|CAD|INR|SAR)\b", scrubbed_text
  )
  if curr_match:
    detected_default_currency = curr_match.group(1)

  for raw_line in scrubbed_text.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("---- File:"):
      continue

    date_match = _LINE_DATE_RE.search(line)
    if not date_match:
      continue

    amount_matches = list(_CURRENCY_AMOUNT_RE.finditer(line))
    if not amount_matches:
      continue

    tx_date = date_match.group(1).strip()

    # Determine primary transaction amount and optional running balance
    primary_match = amount_matches[0]
    balance_val: Decimal | None = None

    if len(amount_matches) >= 2:
      # Check if the last amount is a running balance
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

    # Determine Debit vs Credit
    line_lower = line.lower()
    sign_str = primary_match.group("sign") or ""
    if (
        "credit" in line_lower
        or "salary" in line_lower
        or "deposit" in line_lower
        or "payroll" in line_lower
        or sign_str == "+"
    ) and "debit" not in line_lower:
      tx_type = "Credit"
    else:
      tx_type = "Debit"

    # Extract Merchant and Description from pipe-separated segments or remaining text
    if "|" in line:
      parts = [p.strip() for p in line.split("|") if p.strip()]
      non_meta_parts: list[str] = []
      for p in parts:
        if p == tx_date:
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
          " | ".join(non_meta_parts[1:]) if len(non_meta_parts) > 1 else merchant_name
      )
    else:
      # Remove date and amounts to isolate merchant/description
      cleaned_desc = line[date_match.end() : primary_match.start()].strip(
          " -|:\t"
      )
      if not cleaned_desc:
        cleaned_desc = "Statement Transaction"
      tokens = cleaned_desc.split()
      merchant_name = " ".join(tokens[:2]) if len(tokens) >= 2 else tokens[0]
      description = cleaned_desc

    # Clean up any trailing Ref placeholder from merchant name
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