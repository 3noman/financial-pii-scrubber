from decimal import Decimal
import uuid
from app.database.base import Base
from app.services.analytics import compute_deterministic_analytics
from app.services.database_service import (
    create_verified_statement_with_transactions,
    delete_statement_and_related_data,
    get_chat_history,
    get_latest_analysis,
    get_statement_by_id,
    get_transactions_for_statement,
    save_analysis_result,
    save_chat_message,
)
from app.services.transaction_parser import parse_transactions_from_scrubbed_text
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _create_isolated_test_session() -> Session:
    """Creates an isolated transactional test session with foreign-key enforcement enabled."""
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fks(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    return TestSession()


def test_parse_transactions_and_compute_exact_analytics() -> None:
    scrubbed_sample = (
        "---- File: bank_statement.txt ----\n"
        "Statement for Sarah Ahmed | Account No: <ACCOUNT_ID> | IBAN: <IBAN>\n"
        "2026-10-01 | Employer Corp | Monthly Salary Deposit | Credit | PKR 150,000.00 | Bal: PKR 200,000.00\n"
        "2026-10-03 | Foodpanda | Dinner Order | Ref: <REFERENCE_ID> | Debit | PKR 2,500.00 | Bal: PKR 197,500.00\n"
        "2026-10-05 | Foodpanda | Lunch Order | Ref: <REFERENCE_ID> | Debit | PKR 1,500.00 | Bal: PKR 196,000.00\n"
        "2026-10-08 | Netflix.com | Monthly Subscription | Debit | PKR 1,100.00 | Bal: PKR 194,900.00\n"
        "2026-10-12 | TESCO STORES | Weekly Groceries | Debit | PKR 8,400.00 | Bal: PKR 186,500.00\n"
    )

    parsed = parse_transactions_from_scrubbed_text(scrubbed_sample)
    assert len(parsed) == 5

    metrics = compute_deterministic_analytics(parsed)
    assert metrics["total_income"] == 150000.00
    assert metrics["total_spending"] == 13500.00
    assert metrics["debit_count"] == 4
    assert metrics["credit_count"] == 1
    assert metrics["most_frequent_merchants"][0]["merchant"] == "Foodpanda"
    assert metrics["most_frequent_merchants"][0]["transaction_count"] == 2
    assert metrics["subscription_expenses"]["total"] == 1100.00


def test_database_persistence_and_cascade_deletion() -> None:
    db = _create_isolated_test_session()
    try:
        scrubbed_text = (
            "Account No: <ACCOUNT_ID>\n"
            "2026-10-03 | Foodpanda | Dinner | Debit | PKR 2,500.00\n"
            "2026-10-08 | Netflix.com | Subscription | Debit | PKR 1,100.00\n"
        )
        txs = parse_transactions_from_scrubbed_text(scrubbed_text)

        stmt = create_verified_statement_with_transactions(
            db=db,
            original_filename="october_statement.pdf",
            file_type="pdf",
            scrubbed_content=scrubbed_text,
            verification_passed=True,
            redaction_summary={"<ACCOUNT_ID>": 1},
            parsed_transactions=txs,
        )

        assert stmt.id is not None
        stored_txs = get_transactions_for_statement(db, stmt.id)
        assert len(stored_txs) == 2
        assert stored_txs[0].amount == Decimal("2500.00")

        # Save AI analysis and chat messages linked to statement
        save_analysis_result(
            db, stmt.id, {"total_spending": 3600.0}, "llama-3.3-70b-versatile"
        )
        conv_id = uuid.uuid4()
        save_chat_message(db, stmt.id, conv_id, "user", "How much on Foodpanda?")
        save_chat_message(db, stmt.id, conv_id, "assistant", "You spent PKR 2,500.00.")

        assert get_latest_analysis(db, stmt.id) is not None
        assert len(get_chat_history(db, conv_id, stmt.id)) == 2

        # Delete statement and verify cascade deletion removes all child rows
        deleted = delete_statement_and_related_data(db, stmt.id)
        assert deleted is True
        assert get_statement_by_id(db, stmt.id) is None
        assert get_transactions_for_statement(db, stmt.id) == []
        assert get_latest_analysis(db, stmt.id) is None
        assert get_chat_history(db, conv_id) == []
    finally:
        db.close()
