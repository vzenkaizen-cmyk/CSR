# Vidu Saviya CSR Management System

A Streamlit-based dashboard for managing CSR programmes, site budgets, expenses, payment requests, approvals, scholarships, nursery stock, and planting records.

### Key Features
- Programme and site filtering
- 2026–2027 budget and spending summaries
- Payment requests and admin approvals
- Scholarship and one-time payment management
- Nursery stock and planting records
- CSV report exports

### Getting Started
Install dependencies and run the application:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The system supports SQLite for local development and Neon PostgreSQL for cloud deployment. Initial budget data is imported from the CSR BP 2026–2027 workbook. Payment records affect spending totals only after admin approval.

**Note:** Configure database credentials securely and change the default admin password before deployment.
