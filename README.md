# Financial Data Privacy Scrubber & AI Budget Analyzer

A production-minded, privacy-first personal finance web application that extracts financial statements across multiple formats (PDF, DOCX, CSV, TXT), strips sensitive personal and financial identifiers locally, verifies output through an independent security gate, persists verified scrubbed records in PostgreSQL, computes 100% deterministic financial totals in Python, and generates grounded budgeting insights with follow-up Q&A via Groq AI.

---

## 1. Key Highlights & Privacy Architecture

- **100% Local Privacy Pipeline**: Raw financial documents and unredacted contents are **never** sent to any external API. All extraction, PII detection, masking, and security gate verification occur strictly on your local machine.
- **Context-Aware PII Engine**: Powered by Microsoft Presidio + custom recognizers with checksum validation:
  - **IBAN**: ISO 13616 Modulo-97 verification across international and Pakistani bank formats.
  - **Card Numbers**: Luhn algorithm validation (Visa, Mastercard, Amex, masked cards).
  - **National IDs**: Pakistani CNIC (`XXXXX-XXXXXXX-X`), US SSN, UK NINO, Canadian SIN.
  - **Banking Routing**: SWIFT/BIC, UK Sort Codes, Indian IFSC, US ABA Routing, Canadian Transit.
  - **Account & Trace Identifiers**: Context-aware `<ACCOUNT_ID>`, `<REFERENCE_ID>`, `<PAYMENT_HANDLE>` (UPI, Raast, Nayapay, Sadapay).
  - **International Phones & Addresses**: Google `phonenumbers` integration + street address recognition.
- **Context Preservation**: Strictly preserves account holder names, merchant names (`Foodpanda`, `Netflix.com`, `TESCO STORES`, `Amazon`, `Uber`, `Spotify`), dates, currencies, amounts, and transaction descriptions.
- **Independent Security Gate (Verifier)**: Re-scans scrubbed output with independent regex and checksum audits before database storage or Groq API transmission. If verification fails, external AI calls are completely blocked.
- **Deterministic Accuracy Controls**: Python computes all spending totals, category breakdowns, merchant rankings, and subscription expenses using exact `Decimal` arithmetic. Verified Python calculations override any potential LLM math hallucinations.
- **Prompt-Injection Defense**: Delimits statements inside `<untrusted_financial_data>` tags and strips directive phrases (`IGNORE ALL INSTRUCTIONS`).
- **Grounded AI Chat**: Pre-computed Python metrics and scoped PostgreSQL conversation history ensure zero hallucinations.
- **Modern Fintech UI**: Responsive dashboard built with pure HTML5, CSS3, and Vanilla JavaScript—no external frameworks or CDNs.

---

## 2. Technology Stack

- **Backend**: Python 3.12+, FastAPI, Uvicorn, Pydantic v2, Pydantic Settings
- **Database**: PostgreSQL 16 (Docker Compose), SQLAlchemy 2.0 ORM, psycopg3, Alembic
- **Document Extractors**: `pdfplumber` (PDF text & tables), `python-docx` (Word paragraphs & tables), Python `csv` module (with encoding fallback `utf-8-sig`, `cp1252`, `latin-1`), `pathlib` (TXT)
- **PII & Privacy**: Microsoft Presidio Analyzer & Anonymizer, `spaCy` (`en_core_web_lg`), `phonenumbers`, custom regex & checksum recognizers
- **AI Engine**: Groq Python SDK (`llama-3.3-70b-versatile` with JSON mode)
- **Frontend**: Semantic HTML5, Custom CSS3 (#F8F9FA, #1F2937, #2563EB), Vanilla JavaScript (ES6+)
- **Testing**: `pytest`, FastAPI `TestClient` (21 passing automated tests)

---

## 3. Installation & Setup Instructions (Windows / PowerShell)

### Prerequisites
- Python 3.12+ installed
- Git installed
- Docker Desktop installed (for PostgreSQL) OR native PostgreSQL 16
- Free Groq API Key (from [console.groq.com](https://console.groq.com))

### Step 1: Clone Repository & Create Virtual Environment
```powershell
git clone <your-repo-url>
cd financial-pii-scrubber

# Create Python 3.12 virtual environment
py -3.12 -m venv .venv

# Activate virtual environment
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
.\.venv\Scripts\Activate.ps1