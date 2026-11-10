from pathlib import Path
from app.services.pii.verifier import verify_scrubbed_text
from app.services.processing import process_directory


def test_verifier_passes_clean_scrubbed_text() -> None:
    clean_scrubbed = (
        "Statement for Sarah Ahmed\n"
        "Account No: <ACCOUNT_ID> | IBAN: <IBAN> | CNIC: <NATIONAL_ID>\n"
        "2026-10-01 | Foodpanda | Ref: <REFERENCE_ID> | PKR 2,450.00\n"
        "2026-10-03 | Netflix.com | Monthly Subscription | USD 15.99\n"
    )
    report = verify_scrubbed_text(clean_scrubbed)
    assert report.passed is True
    assert report.findings == []
    assert report.placeholders_verified is True


def test_verifier_blocks_leaked_iban_card_cnic_and_email() -> None:
    leaked_text = (
        "Account Holder: Ali Raza\n"
        "Leaked IBAN: PK36 SCBL 0000 0011 2345 6702\n"
        "Leaked Card: 4532 0151 1283 0366\n"
        "Leaked CNIC: 42101-1234567-1\n"
        "Leaked Email: ali.raza@example.com\n"
    )
    report = verify_scrubbed_text(leaked_text)
    assert report.passed is False
    assert len(report.findings) >= 3
    # Ensure findings never expose the actual raw PII numbers
    findings_str = " ".join(report.findings)
    assert "42101-1234567-1" not in findings_str
    assert "4532 0151 1283 0366" not in findings_str
    assert "ali.raza@example.com" not in findings_str


def test_combined_output_engine_processes_folder_and_isolates_errors(
    tmp_path: Path,
) -> None:
    # 1. Valid TXT statement
    (tmp_path / "bank_statement.txt").write_text(
        "Account Holder: Usman Tariq\n"
        "IBAN: PK36 SCBL 0000 0011 2345 6702\n"
        "2026-10-02 | Foodpanda | PKR 1,500.00\n",
        encoding="utf-8",
    )
    # 2. Valid CSV statement
    (tmp_path / "wallet_transactions.csv").write_text(
        "Date,Merchant,Contact,Amount\n"
        "2026-10-05,Netflix.com,usman@example.com,USD 15.99\n",
        encoding="utf-8",
    )
    # 3. Corrupted PDF file (should fail gracefully without crashing the batch)
    (tmp_path / "corrupted.pdf").write_bytes(b"%PDF-1.7 broken content")
    # 4. Unsupported file format (should be reported as unsupported)
    (tmp_path / "notes.xlsx").write_bytes(b"fake excel bytes")

    summary = process_directory(tmp_path)

    assert summary.total_files == 4
    assert summary.successful_files == 2
    assert summary.failed_files == 2
    assert summary.unsupported_files == 1
    assert summary.verification_passed is True

    # Verify exact required combined header format
    assert "---- File: bank_statement.txt ----" in summary.combined_output
    assert "---- File: wallet_transactions.csv ----" in summary.combined_output
    assert "<IBAN>" in summary.combined_output
    assert "<EMAIL>" in summary.combined_output
    assert "PK36 SCBL 0000 0011 2345 6702" not in summary.combined_output
    assert "usman@example.com" not in summary.combined_output
    assert "Foodpanda" in summary.combined_output
    assert "Netflix.com" in summary.combined_output
