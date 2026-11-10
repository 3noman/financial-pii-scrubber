from collections import defaultdict
from decimal import Decimal
from typing import Any
from app.schemas.schemas import TransactionSchema


def compute_deterministic_analytics(
    transactions: list[TransactionSchema],
) -> dict[str, Any]:
  """Computes 100% deterministic financial totals, merchant rankings, category breakdowns,

  recurring payments, subscription expenses, and monthly patterns in Python.
  """
  total_spending = Decimal("0.00")
  total_income = Decimal("0.00")
  debit_count = 0
  credit_count = 0

  category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
  merchant_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
  merchant_counts: dict[str, int] = defaultdict(int)
  monthly_spending: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
  monthly_income: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

  debit_transactions: list[TransactionSchema] = []
  subscription_items: list[dict[str, Any]] = []

  primary_currency = transactions[0].currency if transactions else "PKR"

  for tx in transactions:
    month_key = tx.transaction_date[:7] if len(tx.transaction_date) >= 7 else "Unknown"

    if tx.transaction_type == "Debit":
      total_spending += tx.amount
      debit_count += 1
      category_totals[tx.category] += tx.amount
      merchant_totals[tx.merchant_name] += tx.amount
      merchant_counts[tx.merchant_name] += 1
      monthly_spending[month_key] += tx.amount
      debit_transactions.append(tx)

      if tx.category == "Subscriptions" or "subscription" in tx.description.lower():
        subscription_items.append({
            "date": tx.transaction_date,
            "merchant": tx.merchant_name,
            "amount": float(tx.amount),
            "currency": tx.currency,
            "description": tx.description,
        })
    else:
      total_income += tx.amount
      credit_count += 1
      monthly_income[month_key] += tx.amount

  # Top merchants by total spend
  top_merchants = [
      {
          "merchant": merchant,
          "total_spent": float(amount),
          "transaction_count": merchant_counts[merchant],
          "currency": primary_currency,
      }
      for merchant, amount in sorted(
          merchant_totals.items(), key=lambda x: x[1], reverse=True
      )[:10]
  ]

  # Most frequent merchants by count
  most_frequent_merchants = [
      {
          "merchant": merchant,
          "transaction_count": count,
          "total_spent": float(merchant_totals[merchant]),
          "currency": primary_currency,
      }
      for merchant, count in sorted(
          merchant_counts.items(),
          key=lambda x: (x[1], merchant_totals[x[0]]),
          reverse=True,
      )[:10]
  ]

  # Largest individual debit transactions
  largest_transactions = [
      {
          "date": tx.transaction_date,
          "merchant": tx.merchant_name,
          "description": tx.description,
          "amount": float(tx.amount),
          "currency": tx.currency,
          "category": tx.category,
      }
      for tx in sorted(debit_transactions, key=lambda t: t.amount, reverse=True)[:5]
  ]

  # Recurring payments (merchants paid 2+ times OR subscription category)
  recurring_payments = [
      {
          "merchant": merchant,
          "occurrences": count,
          "total_spent": float(merchant_totals[merchant]),
          "currency": primary_currency,
      }
      for merchant, count in merchant_counts.items()
      if count >= 2
  ]

  spending_by_category = {
      cat: float(amt)
      for cat, amt in sorted(
          category_totals.items(), key=lambda x: x[1], reverse=True
      )
  }

  subscription_total = sum(
      Decimal(str(item["amount"])) for item in subscription_items
  )

  return {
      "currency": primary_currency,
      "total_transactions": len(transactions),
      "debit_count": debit_count,
      "credit_count": credit_count,
      "total_spending": float(total_spending),
      "total_income": float(total_income),
      "net_cashflow": float(total_income - total_spending),
      "spending_by_category": spending_by_category,
      "top_merchants": top_merchants,
      "most_frequent_merchants": most_frequent_merchants,
      "largest_transactions": largest_transactions,
      "recurring_payments": recurring_payments,
      "subscription_expenses": {
          "total": float(subscription_total),
          "items": subscription_items,
      },
      "monthly_spending": {k: float(v) for k, v in sorted(monthly_spending.items())},
      "monthly_income": {k: float(v) for k, v in sorted(monthly_income.items())},
  }