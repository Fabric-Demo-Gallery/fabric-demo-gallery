# Technical Drawing Analysis

Generic demo for analyzing manufacturing technical drawings with a real
multimodal model. The demo extracts visible drawing information into structured
review data: title block fields, dimensions, tolerances, surface finish, GD&T,
notes, and review flags.

The sample drawings are generated neutral assets. They intentionally contain no
organization, supplier, or company names.

## Local development

Backend:

```bash
cd demos/technical-drawing-analysis
cp backend/.env.example .env
uv run --project backend uvicorn technical_drawing_analysis.app:app --reload
```

Frontend:

```bash
cd demos/technical-drawing-analysis/frontend
corepack enable
corepack prepare pnpm@9.15.9 --activate
pnpm install --frozen-lockfile
pnpm dev
```

The local backend always calls the configured real model. There is no fake or
offline analysis path.

## Configuration

Set these values in `demos/technical-drawing-analysis/.env` for local runs:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>
AZURE_FOUNDRY_MODEL=gpt-5.4
AZURE_TENANT_ID=<tenant-id>
AZURE_AI_SUBSCRIPTION_ID=<subscription-id>
```

## Deployment

The deployed shape is:

```text
Browser
  -> public ACA frontend with Easy Auth
  -> frontend /api proxy
  -> internal-only ACA backend
  -> Azure AI Foundry model endpoint
```

The frontend is protected by ACA Easy Auth. Browser icon paths are excluded from
auth so tabs and touch icons render before sign-in.
