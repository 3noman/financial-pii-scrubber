import json
from typing import Any
from app.config import get_settings
from app.core.exceptions import ExternalAIServiceError, PrivacyVerificationFailedError
from app.core.logging import get_logger
from app.schemas.schemas import TransactionSchema
from app.services.analytics import compute_deterministic_analytics
from app.services.groq_service import (
    load_prompt_file,
    sanitize_untrusted_text_for_prompt,
)
from app.services.pii.verifier import verify_scrubbed_text
from groq import Groq

logger = get_logger(__name__)


def _answer_from_deterministic_python(
    question: str,
    deterministic: dict[str, Any],
    transactions: list[TransactionSchema],
) -> str:
  """Provides a 100% grounded deterministic answer when Groq API key is not configured

  or as a ground-truth reference context.
  """
  q = question.lower().strip()
  curr = deterministic["currency"]
  cats: dict[str, float] = deterministic["spending_by_category"]

  if not transactions:
    return "I cannot determine the answer because no verified transactions were found in the available statement records."

  if "food" in q or "dining" in q or "foodpanda" in q:
    food_total = cats.get("Food & Dining", 0.0)
    fp_txs = [
        t for t in transactions if "foodpanda" in t.merchant_name.lower()
    ]
    fp_sum = float(sum(t.amount for t in fp_txs))
    return (
        f"Based on your confirmed transactions, you spent **{curr} {food_total:,.2f}** "
        f"in the Food & Dining category (including **{curr} {fp_sum:,.2f}** across "
        f"{len(fp_txs)} transaction(s) at Foodpanda)."
    )

  if "most often" in q or "frequent" in q:
    freq = deterministic["most_frequent_merchants"]
    if not freq:
      return "I cannot determine the most frequent merchant from the available records."
    top = freq[0]
    return (
        f"You paid **{top['merchant']}** most often, with **{top['transaction_count']}** "
        f"confirmed transaction(s) totaling **{curr} {top['total_spent']:,.2f}**."
    )

  if "largest" in q or "biggest" in q or "highest" in q:
    largest = deterministic["largest_transactions"]
    if not largest:
      return "No debit transactions were found in your statement records."
    top = largest[0]
    return (
        f"Your largest confirmed expense was **{curr} {top['amount']:,.2f}** at "
        f"**{top['merchant']}** on {top['date']} ({top['description']})."
    )

  if "subscription" in q or "recurring" in q or "netflix" in q or "spotify" in q:
    sub = deterministic["subscription_expenses"]
    items = sub["items"]
    if not items:
      return f"No subscription expenses were identified in your records ({curr} 0.00)."
    names = ", ".join(
        f"{i['merchant']} ({curr} {i['amount']:,.2f})" for i in items
    )
    return (
        f"You spent a confirmed total of **{curr} {sub['total']:,.2f}** on "
        f"{len(items)} subscription transaction(s): {names}."
    )

  if "month" in q or "compare" in q:
    months = deterministic["monthly_spending"]
    if not months:
      return "Monthly spending data is not available in the current statement."
    parts = [f"{m}: {curr} {amt:,.2f}" for m, amt in months.items()]
    return "Here is your confirmed spending by month: " + " | ".join(parts) + "."

  if "category" in q or "most of my expenses" in q:
    if not cats:
      return "No categorized expenses were found in the statement records."
    top_cat, top_val = next(iter(cats.items()))
    return (
        f"**{top_cat}** accounts for the largest share of your expenses at "
        f"**{curr} {top_val:,.2f}** out of **{curr} {deterministic['total_spending']:,.2f}** total spending."
    )

  if "reduce" in q or "save" in q or "budget" in q:
    top_cat = next(iter(cats.keys()), "general expenses")
    return (
        f"Your total confirmed spending is **{curr} {deterministic['total_spending']:,.2f}**. "
        f"To reduce expenses, focus first on **{top_cat}** and review recurring subscriptions "
        f"(currently **{curr} {deterministic['subscription_expenses']['total']:,.2f}**)."
    )

  # Check if the question asks about something completely absent from the records (e.g. crypto, mortgage, tax)
  known_words = " ".join(
      f"{t.merchant_name} {t.description} {t.category}".lower()
      for t in transactions
  )
  query_tokens = [
      w
      for w in q.replace("?", "").split()
      if len(w) > 4
      and w
      not in {
          "spend",
          "spent",
          "total",
          "much",
          "which",
          "where",
          "statement",
          "money",
          "expenses",
      }
  ]
  if query_tokens and not any(tok in known_words for tok in query_tokens):
    return (
        "I cannot determine that from your available statement records. "
        f"Your verified records cover {len(transactions)} transaction(s) totaling "
        f"{curr} {deterministic['total_spending']:,.2f} in spending."
    )

  return (
      f"Based on your {len(transactions)} verified transactions, your total spending is "
      f"**{curr} {deterministic['total_spending']:,.2f}** and total identified income is "
      f"**{curr} {deterministic['total_income']:,.2f}**."
  )


def answer_budget_chat_question(
    question: str,
    scrubbed_text: str,
    transactions: list[TransactionSchema],
    conversation_history: list[dict[str, str]] | None = None,
    groq_client: Any | None = None,
) -> str:
  """Answers a user's budgeting question using predefined Python calculations

  and verified scrubbed context, while blocking prompt injection and unverified data.
  """
  if not question or not question.strip():
    return "Please enter a question about your statement."

  # 1. Enforce Security Gate on scrubbed statement context
  verification = verify_scrubbed_text(scrubbed_text)
  if not verification.passed:
    raise PrivacyVerificationFailedError(verification.findings)

  # 2. Pre-calculate deterministic metrics and baseline grounded answer in Python
  deterministic = compute_deterministic_analytics(transactions)
  grounded_python_answer = _answer_from_deterministic_python(
      question, deterministic, transactions
  )

  settings = get_settings()
  api_key = settings.GROQ_API_KEY.strip()
  if groq_client is None and (
      not api_key or api_key == "your_groq_api_key_here"
  ):
    return grounded_python_answer

  # 3. Build safe context for Groq (never expose raw DB connection or raw PII)
  safe_question = sanitize_untrusted_text_for_prompt(question[:1000])
  tx_lines = [
      f"{t.transaction_date} | {t.merchant_name} | { sanitize_untrusted_text_for_prompt(t.description) } "
      f"| {t.transaction_type} | {t.currency} {t.amount:.2f} | Category: {t.category}"
      for t in transactions[:150]
  ]

  system_prompt = load_prompt_file("chat.txt")
  context_block = (
      "<untrusted_financial_data>\n"
      f"Verified Deterministic Metrics:\n{json.dumps(deterministic, indent=2)}\n\n"
      f"Pre-computed Python Reference Answer: {grounded_python_answer}\n\n"
      "Verified Scrubbed Transactions:\n" + "\n".join(tx_lines) + "\n"
      "</untrusted_financial_data>"
  )

  messages: list[dict[str, str]] = [
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": context_block},
  ]

  if conversation_history:
    for msg in conversation_history[-6:]:
      role = "assistant" if msg.get("role") == "assistant" else "user"
      messages.append({
          "role": role,
          "content": sanitize_untrusted_text_for_prompt(msg.get("message", "")),
      })

  messages.append({"role": "user", "content": safe_question})

  try:
    client = groq_client or Groq(
        api_key=api_key, timeout=settings.GROQ_TIMEOUT_SECONDS
    )
    completion = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.1,
        max_tokens=500,
    )
    reply = (completion.choices[0].message.content or "").strip()
    return reply if reply else grounded_python_answer
  except Exception as exc:
    logger.error(f"Groq chat request failed ({type(exc).__name__}).")
    raise ExternalAIServiceError(
        "We couldn't reach the AI assistant right now. Your saved statements"
        " are safe. Please try again."
    ) from exc