# PharmAssist POC

Proof-of-concept: pharmacist login → JWT → proxy calls to Pharmapi.

## Stack
- **Backend**: FastAPI (Python) + httpx
- **Frontend**: Single HTML file, no build step

## Setup (5 minutes)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at http://127.0.0.1:8000
Auto-docs at http://127.0.0.1:8000/docs

### 2. Frontend

Just open `frontend/index.html` in your browser.
No server needed — it talks directly to the FastAPI backend.

### 3. Demo login

| Field    | Value                   |
|----------|-------------------------|
| Email    | pharmacist@demo.gr      |
| Password | demo123                 |

## Pharmapi credentials

Set via environment variables (or edit main.py directly for POC):

```bash
# Already defaulted in code — only set these if you want to override:
export PHARMAPI_USERNAME=medcare1pharmapi
export PHARMAPI_PASSWORD=Aa900919081908!!
export PHARMAPI_API_KEY=pi2jwygkd07yho3a4dw6jc55tg5ra3uc
```

## What works

| Feature | Endpoint |
|---------|----------|
| Pharmacist login | POST /auth/login |
| Session check | GET /auth/me |
| Pharmapi ping | GET /pharmapi/ping |
| Pharmacy details | GET /pharmapi/pharmacy |
| Load prescription | GET /pharmapi/prescriptions/{barcode} |

## What's NOT in this POC (next steps)

- PostgreSQL database (users, patients, audit log)
- Encrypted Pharmapi credential storage per pharmacy
- Safety engine (drug-drug interactions)
- Patient history / conditions
- Dispense flow
- React frontend with TanStack Query + Zustand

## Auto-generated API docs

FastAPI generates interactive Swagger UI automatically:
http://127.0.0.1:8000/docs

You can test all endpoints directly from the browser there.
