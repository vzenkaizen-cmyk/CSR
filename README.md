# Vidu Saviya CSR Management System

Streamlit CSR dashboard with programme/site filters, 2026–2027 budget seed lines, category-level budget/spend/unspent summaries, payment requests, approval queue, scholarship/one-time payment fields, nursery stock, planting records, and CSV reports.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
# Windows cmd: .venv\\Scripts\\activate.bat
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Without `DATABASE_URL`, the app uses a local SQLite file (`csr_local.db`) for development. For Neon, create a Neon PostgreSQL database, copy its connection string, and set `DATABASE_URL` before starting Streamlit. Keep the Neon connection string private.

PowerShell example:
```powershell
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
streamlit run app.py
```

Streamlit Cloud: add `DATABASE_URL` under **App → Settings → Secrets**:
```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```

The app creates its tables on startup and imports the initial budget seed once. The shared starter login is `admin` / `admin@123`. Change it immediately before deployment; the account-creation feature creates ordinary user accounts, and the admin can promote users from the sidebar.

## Important data notes

- Initial budget lines were extracted from the uploaded `CSR BP 2026-2027 Budget With Details` workbook. Only populated positive budget cells from the programme rows were seeded; empty cells are not treated as zero-budget commitments.
- The uploaded reforestation workbook is not automatically imported as live records. Use the Nursery and Planting forms to enter/update operational records, and reconcile them against the source workbook before production use.
- Payment records start as **Pending** and affect spent/unspent figures only after an admin approves them. This is an operational starter, not an audited finance system.
- Account numbers and other bank details are sensitive. Restrict access, use proper secrets management, and follow company retention and approval policies before production deployment.
