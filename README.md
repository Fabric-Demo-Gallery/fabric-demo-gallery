# Fabric Demo Gallery

One-click deployable industry demos for Microsoft Fabric. Browse industry-specific scenarios, sign in with Azure AD, and deploy a complete Fabric environment — workspace, lakehouse, notebooks, semantic model, reports, and pipelines — into your tenant in minutes.

## Industries

| Industry | Demo | What Gets Created |
|----------|------|-------------------|
| Manufacturing | Quality Control Analytics | Lakehouse, 3 notebooks (Bronze/Silver/Gold), Semantic Model, Report, Pipeline |
| Retail | Sales & Inventory Analytics | Lakehouse, 3 notebooks (Bronze/Silver/Gold), Semantic Model, Report, Pipeline |

## Architecture

```
┌─────────────────────────────────┐
│  Next.js Frontend (Gallery UI)  │
│  - Browse demos                 │
│  - Deployment wizard            │
│  - Live progress tracking       │
└──────────────┬──────────────────┘
               │ REST + SSE
┌──────────────▼──────────────────┐
│  FastAPI Backend                │
│  - Auth (Azure AD / MSAL)       │
│  - Fabric REST API client       │
│  - Deployment orchestrator      │
└──────────────┬──────────────────┘
               │ Fabric REST APIs
┌──────────────▼──────────────────┐
│  Microsoft Fabric Tenant        │
│  - Workspace                    │
│  - Lakehouse + sample data      │
│  - Notebooks (PySpark)          │
│  - Semantic Model (Direct Lake) │
│  - Power BI Report              │
│  - Data Pipeline                │
└─────────────────────────────────┘
```

## Prerequisites

- Azure AD account with access to a Microsoft Fabric capacity (F2+ or Trial)
- Python 3.11+
- Node.js 18+

## Quick Start...

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Fill in Azure AD app registration values
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local  # Fill in backend URL and Azure AD client ID
npm run dev
```

## Adding a New Industry Demo

1. Create a folder under `demos/<industry-slug>/`
2. Add a `manifest.json` following the schema in `demos/schema.json`
3. Add notebooks (`.ipynb`), TMDL definitions, and sample data
4. Submit a PR — CI will validate the manifest against the schema

See [demos/README.md](demos/README.md) for details.

## License

MIT
