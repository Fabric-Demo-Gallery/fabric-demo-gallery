# delivery-note-extraction

Automatische Erfassung gescannter Lieferscheine der Buchbranche im Wareneingang
eines Logistikdienstleisters: Upload eines Scans, parallele Analyse mit Azure
Document Intelligence (Layout/OCR) und einem multimodalen Foundry-Modell
(strukturierte Extraktion mit Konfidenzen), Fundstellen-Mapping ins Dokument,
Prüf-/Korrektur-Workflow und manuelle Messdaten-Erfassung.

Requirements und Schema: [`REQUIREMENTS.md`](REQUIREMENTS.md),
[`data/extraction-schema.md`](data/extraction-schema.md).

## Architektur

```text
Browser
  -> ACA Frontend (Easy Auth, Express, statisches Vite/React-Bundle)
  -> /api Proxy
  -> ACA Backend (FastAPI, internal-only ingress, Managed Identity)
     -> Azure Document Intelligence prebuilt-layout (Woerter, Polygone, Drehwinkel)
     -> Foundry-Modell (Default gpt-5.4, pro Request waehlbar) mit striktem
        Structured Output aus den pydantic-Modellen (Kopf + Positionen,
        confidence / source_text / handwritten_correction / alternatives
        pro Feld)
     -> Fuzzy-Grounding source_text -> DI-Regionen -> Bounding Boxes
        (auch fuer Alternativen, Pfad-Suffix .altN; bei mehreren
        gleichwertigen Fundstellen werden alle als "ambiguous" geliefert)
```

- Pro Analyse streamt `POST /api/analyze/stream` SSE-Events
  (`started`, `layout_started`, `model_started`, `layout_completed`,
  `model_completed`, `grounding_started`, `completed`) inklusive
  gemessener Latenz pro Schritt; die UI zeigt sie im Fortschrittsbalken an
  (OCR und LLM-Extraktion laufen parallel und sind als Gabelung
  visualisiert; gesamt entspricht dem Maximum, nicht der Summe).
- Modellwahl: `GET /api/models` listet zur Laufzeit die multimodalen
  Chat-Deployments des Foundry-Accounts; die UI bietet Modell und
  den je Modell unterstuetzten Reasoning-Aufwand als Dropdowns an. Defaults kommen aus
  `AZURE_FOUNDRY_MODEL` und `AZURE_FOUNDRY_REASONING_EFFORT` (Default
  `none` - der Reasoning-Aufwand dominiert die LLM-Latenz).
- Session-Zustand (Korrekturen, Messdaten, erfasste Lieferscheine) lebt
  ausschliesslich im Browser; das Backend ist zustandslos.
- Alternativen: das LLM liefert pro Feld bis zu 3 alternative Lesarten vom
  Dokument (auch bei hoher Konfidenz, damit sich ein sicher-aber-falscher
  Wert korrigieren laesst), jeweils mit eigener Konfidenz und kurzem
  Herkunfts-Hinweis. Die UI zeigt dafuer einen dezenten "N ⌄"-Toggle am
  Zeilenrand (bei geflaggten Feldern immer sichtbar, sonst beim Hover);
  Klick auf eine Alternative uebernimmt sie wie eine manuelle Korrektur,
  Hover markiert die Fundstelle im PDF.
- Mehrdeutige Fundstellen: taucht ein Wert mehrfach gleich plausibel im
  Dokument auf (z. B. dieselbe Zahl zweimal), waehlt das Grounding nicht
  stillschweigend eine Stelle, sondern liefert alle Treffer (max. 4,
  ueberlappende dedupliziert). Die UI zeichnet sie gestrichelt in Bernstein
  statt Blau und blendet eine Legende ein ("Mehrfach gefunden - Zuordnung
  unsicher").
- Die echten Scans in `data/lieferscheine/` sind **nicht** eingecheckt und
  werden nicht mit ausgeliefert; die App ist Upload-only.
- Observability nach Repo-Standard: OTel nach Application Insights
  selected by the platform contract, Stage-Spans (`pdf_render`, `layout_analysis`,
  `model_extraction`, `grounding`), GenAI-Content-Capture aktiv, Registrierung
  als Foundry External Agent (`delivery-note-extraction`) im Post-Deploy.

## Lokal entwickeln

```bash
cd demos/delivery-note-extraction

# Backend (az login im Foundry-Tenant vorausgesetzt)
cd backend && cp .env.example .env  # Werte eintragen
uv run uvicorn delivery_note_extraction.app:app --port 8000

# Frontend
cd ../frontend
corepack prepare pnpm@9.15.9 --activate
pnpm install --frozen-lockfile
pnpm dev   # proxied /api -> localhost:8000 (siehe vite.config.ts)
```

Checks: `uv run ruff check .` und `uv run mypy src` im Backend,
`pnpm build` im Frontend.

## Evals

[`evals/`](evals/README.md) enthält eine `dne-eval`-CLI für Foundry Cloud
Evals: gpt-5.6-sol/xhigh erzeugt Golden-Extraktionen über die echten Scans,
kleinere Modelle werden mit custom Code-Evaluatoren (Feld-Accuracy nach
Normalisierung und ISBN-Alignment, inkl. „per Alternative rettbar") dagegen
gemessen; die Runs erscheinen vergleichbar im Foundry-Portal. `dne-eval synth`
generiert zusätzlich demo-sichere synthetische Lieferscheine (Faker +
WeasyPrint + augraphy) mit exakter Ground Truth — nutzbar via
`dne-eval --dataset synth …`, da die echten Scans nicht gezeigt werden dürfen.

## Deployment

Azure DevOps Pipeline
`mcaps-microsoft.azure-demos.delivery-note-extraction`
([`azure-pipelines-delivery-note-extraction.yml`](azure-pipelines-delivery-note-extraction.yml)):
validate (ruff, mypy, compileall, pnpm build, Bicep) und deploy (`azd up` in
configured shared resource group, shared ACA environment, and shared ACR, Easy-Auth-Sync,
`tools/verify-deploy.sh` fuer beide Container Apps, External-Agent-
Registrierung, Dashboard-Registry-Upsert).

- Frontend: public + Easy Auth; `/api/health` und die Favicons sind vom Login
  ausgenommen (`/api/health` dient als unauthentifizierter End-to-End-Probe
  Frontend -> Proxy -> Backend).
- Backend: internal-only ingress, ruft Foundry + Document Intelligence ueber
  die Managed Identity (Rollen `Azure AI User` + `Cognitive Services User` auf
  dem bestehenden Foundry-Account).
- Pipeline-Variablen: `AAD_CLIENT_ID`, `AAD_APP_OBJECT_ID`,
  `AAD_CLIENT_SECRET` (secret), `REGISTRY_WRITE_TOKEN` (secret).
