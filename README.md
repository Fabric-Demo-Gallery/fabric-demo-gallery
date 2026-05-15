# Fabric Demo Gallery

One-click deployable industry demos for Microsoft Fabric. Browse industry-specific scenarios, sign in with Microsoft Entra, and deploy a complete Fabric environment — workspace, lakehouse, eventhouse, notebooks, semantic models, Power BI reports, real-time dashboards, and pipelines — into your tenant in minutes.

**Live site:** [https://witty-sand-077be5f03.7.azurestaticapps.net](https://witty-sand-077be5f03.7.azurestaticapps.net)

## Demos

| Industry | Demo | Fabric Items | Time |
|----------|------|-------------|------|
| Manufacturing | Quality Control Analytics | Lakehouse, 5 Notebooks, Semantic Model (30+ measures), 4-page Power BI Report, Pipeline | 8–12 min |
| Retail | Sales & Inventory Analytics | Lakehouse, 3 Notebooks, Star-Schema Semantic Model (6 tables, 37+ measures), 3-page Power BI Report, Pipeline | 8–12 min |
| Energy & Utilities | Smart Grid Monitoring | Lakehouse, Eventhouse, KQL Database, 3 Notebooks, Real-Time Dashboard, Semantic Model, Power BI Report, Pipeline (auto-scheduled every 10 min) | 10–15 min |

## Features

- **One-click deployment** — Select a demo, pick your capacity, click Deploy
- **Live progress streaming** — Real-time SSE updates as each Fabric item is provisioned
- **Stop button** — Cancel deployment mid-flight and clean up partial workspaces
- **Real-time data** — Energy demo includes a simulator notebook that generates live data every 10 minutes
- **Multi-tenant auth** — Works across Azure AD tenants with MSAL redirect login
- **Custom client ID support** — Users from restricted tenants can use `?clientId=THEIR_APP_ID` to bring their own app registration
- **Workspace cleanup** — One-click delete of deployed workspaces

## Architecture

```
┌─────────────────────────────────────┐
│  Next.js Frontend (Static Export)   │
│  Azure Static Web Apps              │
│  - Demo gallery with Fluent UI      │
│  - MSAL auth (redirect + popup)     │
│  - SSE deployment progress          │
│  - Fabric capacity picker (direct)  │
└──────────────┬──────────────────────┘
               │ REST + SSE
┌──────────────▼──────────────────────┐
│  FastAPI Backend                    │
│  Azure App Service (Python 3.12)    │
│  - Fabric REST API client           │
│  - Deployment orchestrator          │
│  - Rate limiting (slowapi)          │
│  - Input validation                 │
└──────────────┬──────────────────────┘
               │ Fabric REST APIs + OneLake DFS
┌──────────────▼──────────────────────┐
│  Microsoft Fabric Tenant            │
│  - Workspace + Capacity             │
│  - Lakehouse + sample CSV data      │
│  - Eventhouse + KQL Database        │
│  - Notebooks (PySpark)              │
│  - Semantic Model (Direct Lake)     │
│  - Power BI Report (PBIR-Legacy)    │
│  - Real-Time Dashboard (KQL)        │
│  - Data Pipeline (scheduled)        │
└─────────────────────────────────────┘
```

## Prerequisites

- Microsoft Entra (Azure AD) account with access to a Microsoft Fabric capacity (F2+ or Trial)
- Python 3.11+
- Node.js 18+

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Fill in Azure AD app registration values
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local  # Fill in backend URL and Azure AD client ID
npm run dev
```

Visit `http://localhost:3000` to browse demos.

## Azure Deployment

### Backend (App Service)
```bash
az webapp deploy --name YOUR_APP_NAME --resource-group YOUR_RG \
  --src-path backend-deploy.zip --type zip
```

### Frontend (Static Web Apps)
```bash
cd frontend && npx next build
swa deploy out --deployment-token YOUR_TOKEN --env production
```

## Security

- CORS restricted to known frontend origins
- No `shell=True` in subprocess calls
- `az CLI` token fallback disabled in production
- Input validation on all API parameters (demo IDs, workspace names, UUIDs)
- Rate limiting: 5 deploys/hour, 10 deletes/hour per IP
- API docs (`/docs`, `/redoc`) disabled in production

## Project Structure

```
fabric-demo-gallery/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, rate limiting
│   │   ├── auth.py              # MSAL token handling
│   │   ├── deployer.py          # Deployment orchestrator
│   │   ├── fabric_client.py     # Fabric REST API wrapper
│   │   ├── report_builder.py    # Power BI report definitions
│   │   └── routers/             # API endpoints
│   └── requirements.txt
├── demos/
│   ├── manufacturing-qc/        # Manufacturing demo
│   ├── retail-sales/            # Retail demo
│   ├── energy-grid/             # Energy RTI demo
│   ├── schema.json              # Manifest schema
│   └── generate_sample_data.py  # Data generator
├── frontend/
│   ├── src/app/                 # Next.js pages
│   ├── src/lib/                 # MSAL, auth provider
│   └── public/icons/            # Fabric workload icons
└── CONTRIBUTING.md              # Detailed contributor guide
```

## Adding a New Demo

See [CONTRIBUTING.md](CONTRIBUTING.md) for a detailed guide on adding industry demos, including notebook format requirements, semantic model patterns, and Power BI report building.

## License

MIT
