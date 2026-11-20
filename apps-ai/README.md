# Apps & AI demos

AI applications that the gallery deploys into the user's **Azure subscription**
(not a Fabric workspace). They are listed on the Manufacturing industry page and
live at `/apps/<id>` on the site.

| App | Folder | Model (first available wins) |
| --- | --- | --- |
| Technical Drawing Analysis | [`technical-drawing-analysis/`](technical-drawing-analysis/) | gpt-5.4, gpt-5.4-mini, gpt-4.1 |
| Delivery Note Extraction | [`delivery-note-extraction/`](delivery-note-extraction/) | gpt-5.4, gpt-5.4-mini, gpt-4.1-mini |
| Demand Portfolio Planning | [`demand-portfolio-planning/`](demand-portfolio-planning/) | gpt-5.4-mini, gpt-5.4, gpt-4.1-mini |

The application code comes from the Manufacturing Demos for DACH repository
(`Apps&AI/azure-demos`). Only the runnable app parts are kept here (backend,
frontend, agent instructions); the original `azd` infrastructure, pipelines, and
Easy Auth scripts are replaced by the gallery's own deployment path.

## How a deployment works

Every app has the same shape: a public frontend Container App (React + Express)
proxies `/api` to an internal-only backend Container App (FastAPI), which calls a
Foundry model with its system-assigned managed identity. No keys or secrets.

The gallery backend ([`backend/app/apps_ai.py`](../backend/app/apps_ai.py)) runs
the deployment with the signed-in user's own Azure Resource Manager token. It
needs no extra consent beyond the Azure scenarios that already exist:

1. Pre-flight: checks the caller can create resource groups and role assignments,
   and ranks the model candidates by GlobalStandard quota in the chosen region.
2. Creates a **new, dedicated resource group** (`rg-fdg-<app>-<random>`).
3. Registers the needed resource providers.
4. Creates a Foundry account and project, then deploys the first model that succeeds.
5. Deploys [`infra/main.bicep`](infra/main.bicep), compiled to
   [`demos/_apps/container-apps.json`](../demos/_apps/container-apps.json): Log
   Analytics, Application Insights, the Container Apps environment, both apps,
   and the backend's `Azure AI User` + `Cognitive Services User` roles on the
   Foundry account.
6. Waits until both revisions are running.

A failed deployment deletes its resource group. The Monitoring page's **Delete**
action deletes it for finished deployments.

### Access control

The original demos sit behind Container Apps Easy Auth, which needs an Entra app
registration per deployment (Microsoft Graph and admin consent). To keep the
gallery's consent model unchanged, the frontend is instead restricted with
Container Apps **IP security restrictions**. The deploy panel pre-fills the
caller's public IPv4; the user can edit the list or explicitly choose public
access.

On some corporate networks, traffic to Azure leaves through a different egress IP
than general internet traffic. If the app answers `RBAC: access denied`, add the
IP Azure sees under the frontend Container App's **Ingress** settings.

## Container images

[`.github/workflows/apps-ai-images.yml`](../.github/workflows/apps-ai-images.yml)
builds six images on every change under `apps-ai/`. Pushes to `main` publish them
as `ghcr.io/fabric-demo-gallery/fabric-demo-gallery/<app>-<backend|frontend>`
with the `latest` tag and a `sha-<commit>` tag; pull requests only build.

After the first publish, set each of the six GHCR packages to **Public** under
the organization's Packages settings. Container Apps pulls them anonymously.

For testing against another registry, set `APPS_AI_IMAGE_REGISTRY` and/or
`APPS_AI_IMAGE_TAG` on the gallery backend.

## Changing the template

Edit [`infra/main.bicep`](infra/main.bicep), then recompile:

```bash
az bicep build --file apps-ai/infra/main.bicep --outfile demos/_apps/container-apps.json
```

## Adding an app

1. Add the app's `backend/` and `frontend/` here. The frontend must proxy `/api`
   to `BACKEND_URL` and listen on 8080. The backend must read
   `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_FOUNDRY_MODEL` and authenticate with
   `DefaultAzureCredential`.
2. Add it to the image workflow matrix.
3. Add the deployment spec to [`demos/_apps/apps.json`](../demos/_apps/apps.json):
   prefix of 8 characters or fewer, backend port, extra env, model candidates.
4. Add the display entry to
   [`frontend/src/lib/appsCatalog.ts`](../frontend/src/lib/appsCatalog.ts) with the
   same id, and the page to `frontend/public/sitemap.xml`.

## Running an app locally

Each app's own README describes local development. In short: point the backend
at a Foundry project with `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_FOUNDRY_MODEL`,
sign in with `az login`, and start the frontend with `BACKEND_URL` set.
