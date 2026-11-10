from collections.abc import Generator
from app.database.base import Base
from app.database.connection import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Use an in-memory SQLite StaticPool for fast, isolated API route testing
_TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)


@event.listens_for(_TEST_ENGINE, "connect")
def _enable_fks(dbapi_conn, conn_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


Base.metadata.create_all(bind=_TEST_ENGINE)
_TestingSessionLocal = sessionmaker(bind=_TEST_ENGINE, expire_on_commit=False)


def _override_get_db() -> Generator[Session, None, None]:
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def test_complete_api_workflow_upload_verify_analyze_chat_and_delete() -> None:
    # 1. Upload two statement files (TXT and CSV)
    txt_content = (
        "Statement for Sarah Ahmed\n"
        "Account No: 0192-8877665-01 | IBAN: PK36 SCBL 0000 0011 2345 6702\n"
        "CNIC: 42101-7654321-9 | Email: sarah@example.com\n"
        "2026-10-01 | Employer Corp | Monthly Salary Deposit | Credit | PKR 120,000.00\n"
        "2026-10-03 | Foodpanda | Dinner Order | Ref: TXN-11223344 | Debit | PKR 2,500.00\n"
        "2026-10-08 | Netflix.com | Monthly Subscription | Debit | PKR 1,100.00\n"
    ).encode("utf-8")

    csv_content = (
        "Date,Merchant,Description,Type,Amount\n"
        "2026-10-10,TESCO STORES,Weekly Groceries,Debit,PKR 6,400.00\n"
    ).encode("utf-8")

    upload_res = client.post(
        "/api/statements/upload",
        files=[
            ("files", ("bank_statement.txt", txt_content, "text/plain")),
            ("files", ("wallet.csv", csv_content, "text/csv")),
        ],
    )
    assert upload_res.status_code == 200
    # Check security headers
    assert upload_res.headers["X-Content-Type-Options"] == "nosniff"
    assert upload_res.headers["X-Frame-Options"] == "DENY"

    payload = upload_res.json()
    assert payload["status"] == "success"
    assert payload["total_files"] == 2
    assert payload["successful_files"] == 2
    assert payload["verification_passed"] is True
    assert "---- File: bank_statement.txt ----" in payload["combined_output"]
    assert "---- File: wallet.csv ----" in payload["combined_output"]
    assert "PK36 SCBL" not in payload["combined_output"]
    assert "<IBAN>" in payload["combined_output"]

    stmt_id = payload["files"][0]["statement_id"]
    assert stmt_id is not None

    # 2. Retrieve statement verification status
    ver_res = client.get(f"/api/statements/{stmt_id}/verification")
    assert ver_res.status_code == 200
    assert ver_res.json()["verification_passed"] is True
    assert ver_res.json()["safe_for_ai_analysis"] is True

    # 3. Retrieve scrubbed content
    scrub_res = client.get(f"/api/statements/{stmt_id}/scrubbed")
    assert scrub_res.status_code == 200
    assert "<ACCOUNT_ID>" in scrub_res.json()["scrubbed_content"]

    # 4. Retrieve parsed transactions
    tx_res = client.get(f"/api/statements/{stmt_id}/transactions")
    assert tx_res.status_code == 200
    assert tx_res.json()["count"] == 3
    assert tx_res.json()["summary"]["total_spending"] == 3600.00

    # 5. Generate AI analysis
    analyze_res = client.post(f"/api/statements/{stmt_id}/analyze")
    assert analyze_res.status_code == 200
    analysis_data = analyze_res.json()["analysis"]
    assert analysis_data["confirmed_transaction_data"]["total_spending"] == 3600.00

    # 6. Ask a follow-up question via Grounded Chat endpoint
    chat_res = client.post(
        "/api/chat",
        json={
            "statement_id": stmt_id,
            "question": "How much did I spend on food?",
        },
    )
    assert chat_res.status_code == 200
    chat_json = chat_res.json()
    assert "2,500.00" in chat_json["answer"]
    conv_id = chat_json["conversation_id"]

    # 7. Retrieve conversation history
    hist_res = client.get(f"/api/chat/{conv_id}")
    assert hist_res.status_code == 200
    assert hist_res.json()["message_count"] == 2

    # 8. Delete statement and verify 404 afterward
    del_res = client.delete(f"/api/statements/{stmt_id}")
    assert del_res.status_code == 200
    assert client.get(f"/api/statements/{stmt_id}").status_code == 404
