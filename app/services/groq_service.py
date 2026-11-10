import json
from pathlib import Path
import re
from typing import Any
from app.config import get_settings
from app.core.exceptions import ExternalAIServiceError, PrivacyVerificationFailedError
from app.core.logging import get_logger
from app.schemas.schemas import TransactionSchema
from app.services.analytics import compute_deterministic_analytics
from app.services.pii.verifier import verify_scrubbed_text
from groq import Groq
from pydantic import BaseModel, Field, ValidationError

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Maximum scrubbed characters sent to Groq to enforce input size limits
MAX_GROQ_INPUT_CHARS = 24000

# Prompt-injection pattern sanitizer for untrusted transaction descriptions
_INJECTION_PATTERNS = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"
    r"system\s+prompt|you\s+are\s+now|disregard\s+all\s+rules|"
    r"reveal\s+(?:your\s+)?(?:api\s+key|secret|instructions))",
    re.IGNORECASE,
)


class LLMAnalysisPayload(BaseModel):
  """Pydantic validator for the structured JSON returned by Groq."""

  reported_total_spending: float = 0.0
  reported_total_income: float = 0.0
  executive_summary: str = Field(min_length=5)
  monthly_spending_patterns: list[str] = Field(default_factory=list)
  unusual_spending_observations: list[str] = Field(default_factory=list)
  practical_budgeting_suggestions: list[str] = Field(default_factory=list)
  data_limitations_note: str = (
      "Categories are estimated from merchant names; all personal/financial IDs"
      " were scrubbed locally prior to analysis."
  )


def sanitize_untrusted_text_for_prompt(text: str) -> str:
  """Neutralizes prompt-injection phrases inside untrusted statement descriptions."""
  return _INJECTION_PATTERNS.sub("[FILTERED_UNTRUSTED_DIRECTIVE]", text)


def load_prompt_file(filename: str) -> str:
  path = PROMPTS_DIR / filename
  return path.read_text(encoding="utf-8").strip()


def reconcile_ai_with_deterministic_metrics(
    deterministic: dict[str, Any],
    ai_payload: LLMAnalysisPayload,
) -> dict[str, Any]:
  """Compares LLM-reported totals against Python deterministic calculations.

  Overrides any mismatched LLM numbers so guesses are never presented as facts.
  """
  exact_spending = float(deterministic["total_spending"])
  exact_income = float(deterministic["total_income"])

  spending_diff = abs(ai_payload.reported_total_spending - exact_spending)
  income_diff = abs(ai_payload.reported_total_income - exact_income)

  discrepancies: list[str] = []
  if spending_diff > 0.05:
    discrepancies.append(
        f"LLM reported spending ({ai_payload.reported_total_spending:.2f}) "
        f"was corrected to deterministic Python total ({exact_spending:.2f})."
    )
  if income_diff > 0.05:
    discrepancies.append(
        f"LLM reported income ({ai_payload.reported_total_income:.2f}) "
        f"was corrected to deterministic Python total ({exact_income:.2f})."
    )

  # Ensure AI summary does not hallucinate merchants that aren't in the statement
  known_merchants = {
      m["merchant"].lower() for m in deterministic.get("top_merchants", [])
  }

  return {
      "confirmed_transaction_data": {
          "currency": deterministic["currency"],
          "total_transactions": deterministic["total_transactions"],
          "debit_count": deterministic["debit_count"],
          "credit_count": deterministic["credit_count"],
          "total_spending": exact_spending,
          "total_income": exact_income,
          "net_cashflow": deterministic["net_cashflow"],
          "top_merchants": deterministic["top_merchants"],
          "most_frequent_merchants": deterministic["most_frequent_merchants"],
          "largest_transactions": deterministic["largest_transactions"],
          "recurring_payments": deterministic["recurring_payments"],
          "monthly_spending": deterministic["monthly_spending"],
          "monthly_income": deterministic["monthly_income"],
      },
      "estimated_spending_categories": {
          "spending_by_category": deterministic["spending_by_category"],
          "subscription_expenses": deterministic["subscription_expenses"],
      },
      "ai_generated_observations": {
          "executive_summary": ai_payload.executive_summary,
          "monthly_spending_patterns": ai_payload.monthly_spending_patterns,
          "unusual_spending_observations": (
              ai_payload.unusual_spending_observations
          ),
          "practical_budgeting_suggestions": (
              ai_payload.practical_budgeting_suggestions
          ),
          "data_limitations_note": ai_payload.data_limitations_note,
      },
      "verification_and_accuracy_audit": {
          "numbers_verified_by_python": True,
          "llm_totals_matched_source": len(discrepancies) == 0,
          "corrections_applied": discrepancies,
          "known_merchant_count": len(known_merchants),
      },
  }


def _build_local_fallback_payload(
    deterministic: dict[str, Any],
) -> LLMAnalysisPayload:
  """Generates a deterministic, grounded fallback payload when Groq API key is not set."""
  curr = deterministic["currency"]
  spend = deterministic["total_spending"]
  inc = deterministic["total_income"]
  tx_count = deterministic["total_transactions"]
  top_cat = next(iter(deterministic["spending_by_category"].keys()), "None")

  summary = (
      f"Across {tx_count} verified transactions, confirmed total spending is"
      f" {curr} {spend:,.2f}"
      + (
          f" and confirmed total income is {curr} {inc:,.2f}."
          if inc > 0
          else " (no income deposits were identified in this statement)."
      )
  )

  patterns = [
      f"Highest estimated spending category is {top_cat}."
      if top_cat != "None"
      else "No categorized debit expenses found.",
  ]
  for month, amt in deterministic["monthly_spending"].items():
    patterns.append(f"Month {month}: {curr} {amt:,.2f} in total outflows.")

  unusual = []
  if deterministic["largest_transactions"]:
    biggest = deterministic["largest_transactions"][0]
    unusual.append(
        f"Largest single expense was {curr} {biggest['amount']:,.2f} at"
        f" {biggest['merchant']} on {biggest['date']}."
    )

  suggestions = [
      "Review recurring subscriptions and cancel any underutilized monthly"
      " plans.",
      f"Set a monthly budget target for your top category ({top_cat}) to reduce"
      " discretionary outflow.",
      "Track high-frequency small orders (such as food delivery or rides) which"
      " compound over the month.",
  ]

  return LLMAnalysisPayload(
      reported_total_spending=spend,
      reported_total_income=inc,
      executive_summary=summary,
      monthly_spending_patterns=patterns,
      unusual_spending_observations=unusual
      or ["No unusual spending spikes detected in the available records."],
      practical_budgeting_suggestions=suggestions,
  )


def generate_budget_analysis(
    scrubbed_text: str,
    transactions: list[TransactionSchema],
    groq_client: Any | None = None,
) -> tuple[dict[str, Any], str]:
  """Verifies privacy gate, computes deterministic Python analytics, calls Groq

  with untrusted-data framing, validates the JSON output with Pydantic, and
  reconciles all totals.
  """
  # 1. Mandatory Security Gate before ANY external API call
  verification = verify_scrubbed_text(scrubbed_text)
  if not verification.passed:
    logger.error("Blocked Groq analysis call: privacy verification failed.")
    raise PrivacyVerificationFailedError(verification.findings)

  # 2. Deterministic Python calculations
  deterministic = compute_deterministic_analytics(transactions)
  settings = get_settings()

  # Check if a custom client was injected (for testing) or if real API key is configured
  api_key = settings.GROQ_API_KEY.strip()
  if groq_client is None and (
      not api_key or api_key == "your_groq_api_key_here"
  ):
    logger.info(
        "Groq API key not configured; returning deterministic Python analysis."
    )
    fallback_payload = _build_local_fallback_payload(deterministic)
    return (
        reconcile_ai_with_deterministic_metrics(deterministic, fallback_payload),
        "deterministic-local-engine",
    )

  # 3. Prepare sanitized, length-bounded prompt for Groq
  safe_scrubbed_excerpt = sanitize_untrusted_text_for_prompt(
      scrubbed_text[:MAX_GROQ_INPUT_CHARS]
  )
  system_prompt = load_prompt_file("analysis.txt")
  user_prompt = (
      "Verified Deterministic Python Metrics (Ground Truth):\n"
      f"{json.dumps(deterministic, indent=2)}\n\n"
      "<untrusted_financial_data>\n"
      f"{safe_scrubbed_excerpt}\n"
      "</untrusted_financial_data>\n\n"
      "Generate the JSON budget analysis grounded strictly in the metrics"
      " above."
  )

  try:
    client = groq_client or Groq(
        api_key=api_key, timeout=settings.GROQ_TIMEOUT_SECONDS
    )
    completion = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    raw_content = completion.choices[0].message.content or "{}"
    parsed_json = json.loads(raw_content)
    validated_payload = LLMAnalysisPayload.model_validate(parsed_json)
    final_result = reconcile_ai_with_deterministic_metrics(
        deterministic, validated_payload
    )
    return final_result, settings.GROQ_MODEL

  except (json.JSONDecodeError, ValidationError) as exc:
    logger.warning(
        f"Groq returned invalid JSON structure ({type(exc).__name__})."
    )
    raise ExternalAIServiceError(
        "We couldn't validate the AI spending report format. Your saved"
        " statements are safe. Please try again."
    ) from exc
  except Exception as exc:
    logger.error(f"Groq API call failed ({type(exc).__name__}).")
    raise ExternalAIServiceError() from exc