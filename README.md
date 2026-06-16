# Fabric Demo Gallery

One-click deployable industry demos for Microsoft Fabric. Browse industry-specific scenarios, sign in with Microsoft Entra, and deploy a complete Fabric environment into your own tenant in minutes — workspace, lakehouse, notebooks, semantic models, Power BI reports, and more, depending on the scenario you pick.

**Live site:** [https://www.fabricdemogallery.com](https://www.fabricdemogallery.com)

## Demos

Twelve industries are available, each with a ready-to-deploy **Standard** demo plus a set of **Custom** deployment scenarios:

| Industry group | Examples |
|----------------|----------|
| Manufacturing, Retail, Energy & Utilities | Quality control, sales & inventory, smart-grid monitoring |
| Financial Services, Healthcare, Technology | Risk & fraud, patient & care quality, SaaS product analytics |
| Transportation, Construction, Professional Services | Fleet & route, project cost, utilisation & margin |
| Media, Education, Hospitality | Subscriber & content, student outcomes, guest experience |

### Deployment scenarios

Every industry can be deployed as a **Standard** medallion demo, or via a **Custom** scenario:

- **AI & Machine Learning** — feature engineering, SynapseML LightGBM training, evaluation, and batch scoring with risk rankings
- **External Database Integration (Mirroring)** — provisions an Azure SQL Database (Microsoft Entra-only auth), seeds it with operational data, and mirrors it live into Fabric OneLake (zero-ETL)
- **Data Virtualization & Batch Analytics (Shortcuts)** — provisions ADLS Gen2, connects external data in place via Fabric Shortcuts, then processes Bronze → Silver → Gold

## Features

- **One-click deployment** — Select an industry and scenario, pick your capacity, click Deploy
- **Live progress streaming** — Real-time SSE updates as each Fabric item is provisioned
- **12 industries + custom scenarios** — Standard medallion demos plus AI/ML, Mirroring, and Shortcuts
- **Secure mirroring** — Azure SQL with Microsoft Entra-only auth and a secret-less Fabric Workspace Identity
- **Auto-teardown on failure** — A failed deploy best-effort removes the workspace and any Azure SQL server it created, so nothing is left orphaned
- **Capacity pre-flight** — Fails fast with a clear message if the target Fabric capacity is paused
- **Stop button** — Cancel a deployment mid-flight
- **Workspace cleanup** — One-click delete of a deployed workspace (and its Azure SQL server, for mirroring)
- **Multi-tenant auth** — Works across Microsoft Entra tenants with MSAL redirect login
- **Custom client ID support** — Users from restricted tenants can use `?clientId=THEIR_APP_ID` to bring their own app registration

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
               │ Fabric REST APIs + OneLake DFS + ARM
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
│  - Mirrored Database (zero-ETL)     │
└──────────────┬──────────────────────┘
               │ (mirroring scenario)
┌──────────────▼──────────────────────┐
│  Azure (via ARM)                    │
│  - Azure SQL Database (Entra-only)  │
│  - Workspace Identity auth          │
│  - ADLS Gen2 (shortcuts scenario)   │
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
cd frontend
# The backend URL is baked into the static export at build time — set it explicitly
# so the deployed site points at the production API (not localhost). The build will
# fail fast if this is missing or points at localhost.
NEXT_PUBLIC_BACKEND_URL=https://fabric-demo-gallery-api.azurewebsites.net npx next build
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
│   │   ├── deployer.py          # Deployment orchestrator (standard + mirroring)
│   │   ├── fabric_client.py     # Fabric REST API wrapper
│   │   ├── azure_client.py      # ARM client (Azure SQL, ADLS, storage)
│   │   ├── report_builder.py    # Power BI report definitions
│   │   └── routers/             # API endpoints
│   └── requirements.txt
├── demos/
│   ├── <12 industry folders>/   # manufacturing-qc, retail-sales, healthcare, …
│   │   ├── manifest.json        # Standard demo definition
│   │   ├── manifest.custom.json # Offered custom scenarios
│   │   ├── mirroring.json       # Per-sector mirroring spec
│   │   ├── data/                # Sample CSVs
│   │   └── notebooks/           # Per-scenario notebooks (incl. ml/)
│   └── _scenarios/              # Shared scenario templates + mirroring notebooks
├── frontend/
│   ├── src/app/                 # Next.js pages (gallery, demo detail, monitoring)
│   ├── src/lib/                 # MSAL, auth provider, error mapping
│   └── public/                  # Fabric icons, demo video, SWA config
├── tools/                       # validate_mirroring_specs.py and other helpers
├── docs/                        # Pre-demo checklist and notes
└── CONTRIBUTING.md              # Detailed contributor guide
```

## Adding a New Demo

See [CONTRIBUTING.md](CONTRIBUTING.md) for a detailed guide on adding industry demos, including notebook format requirements, semantic model patterns, and Power BI report building.

## License

MIT
