import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import * as pdfjs from "pdfjs-dist"
import type { PDFDocumentProxy } from "pdfjs-dist"
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl

// ── Confidence thresholds (single source of truth for the review flow) ──────
const CONFIDENCE_GREEN = 0.9
const CONFIDENCE_AMBER = 0.7

// ── API types (mirror backend pydantic models, snake_case) ──────────────────

type AlternativeDto = {
  value: string | number | null
  confidence: number
  hint: string | null
}

type ExtractedFieldDto = {
  value: string | number | null
  confidence: number
  source_text: string | null
  handwritten_correction: boolean
  alternatives?: AlternativeDto[]
}

type PositionDto = {
  titel: ExtractedFieldDto
  isbn: ExtractedFieldDto
  auflage: ExtractedFieldDto
  menge: ExtractedFieldDto
  paletten: ExtractedFieldDto
  seite: number | null
}

type ExtractionDto = {
  kopf: Record<KopfFieldName, ExtractedFieldDto>
  positionen: PositionDto[]
  hinweise: string[]
}

type NormPoint = { x: number; y: number }
type NormBox = { x1: number; y1: number; x2: number; y2: number }

type PageWordDto = { text: string; polygon_norm: NormPoint[]; bbox_norm: NormBox }

type PageLayoutDto = {
  page: number
  angle: number
  width: number
  height: number
  unit: string
  words: PageWordDto[]
}

type ReferenceDto = {
  field_path: string
  page: number
  match_score: number
  region_text: string
  polygon_norm: NormPoint[]
  bbox_norm: NormBox
  ambiguous?: boolean
}

type TimingsDto = {
  ocr_ms: number | null
  llm_ms: number | null
  grounding_ms: number | null
  total_ms: number | null
}

type ModelOptionDto = {
  name: string
  model: string
  supportsReasoningEffort: boolean
  reasoningEfforts: string[]
}

type ModelsDto = {
  models: ModelOptionDto[]
  defaultModel: string
  defaultEffort: string | null
}

const EFFORT_LABELS: Record<string, string> = {
  none: "keine",
  minimal: "minimal",
  low: "niedrig",
  medium: "mittel",
  high: "hoch",
  xhigh: "sehr hoch",
  max: "maximal",
}

type AnalyzeResponseDto = {
  sample_id: string | null
  file_name: string
  model: string
  reasoning_effort: string | null
  pages: PageLayoutDto[]
  extraction: ExtractionDto
  derived: {
    anzahl_positionen: number
    gesamtmenge: number | null
    gesamt_paletten: number | null
  }
  references: ReferenceDto[]
  timings: TimingsDto
}

// ── UI state types ───────────────────────────────────────────────────────────

type KopfFieldName = "lieferant" | "verlag" | "lieferschein_nummer" | "herkunftstext" | "datum"
type PositionFieldName = "titel" | "isbn" | "auflage" | "menge" | "paletten"

const KOPF_FIELDS: { name: KopfFieldName; label: string }[] = [
  { name: "lieferant", label: "Lieferant" },
  { name: "verlag", label: "Verlag" },
  { name: "lieferschein_nummer", label: "Lieferschein-Nr." },
  { name: "herkunftstext", label: "Herkunftstext" },
  { name: "datum", label: "Datum" },
]

const POSITION_FIELDS: { name: PositionFieldName; label: string; numeric: boolean }[] = [
  { name: "titel", label: "Titel", numeric: false },
  { name: "isbn", label: "ISBN", numeric: false },
  { name: "auflage", label: "Auflage", numeric: false },
  { name: "menge", label: "Menge", numeric: true },
  { name: "paletten", label: "Paletten", numeric: true },
]

type UiAlternative = {
  value: string
  confidence: number
  hint: string | null
}

type UiField = {
  path: string
  label: string
  numeric: boolean
  original: string
  current: string
  confidence: number
  sourceText: string | null
  handwritten: boolean
  corrected: boolean
  confirmed: boolean
  discarded: boolean
  alternatives: UiAlternative[]
}

type StepState = { status: "pending" | "active" | "done" | "error"; ms: number | null }

type Steps = { upload: StepState; ocr: StepState; llm: StepState }

const IDLE_STEPS: Steps = {
  upload: { status: "pending", ms: null },
  ocr: { status: "pending", ms: null },
  llm: { status: "pending", ms: null },
}

type MessDaten = {
  breite: string
  laenge: string
  hoehe: string
  gewicht: string
  kartonGewicht: string
  verbundGewicht: string
  folieGewicht: string
  fbS22Checked: boolean
  comp1Checked: boolean
  comp4Checked: boolean
  fbS22: string
  comp1: string
  comp4: string
  autostore: boolean
}

const EMPTY_MESSDATEN: MessDaten = {
  breite: "",
  laenge: "",
  hoehe: "",
  gewicht: "",
  kartonGewicht: "",
  verbundGewicht: "",
  folieGewicht: "",
  fbS22Checked: false,
  comp1Checked: false,
  comp4Checked: false,
  fbS22: "",
  comp1: "",
  comp4: "",
  autostore: false,
}

type CompletedNote = {
  fileName: string
  lieferscheinNummer: string
  positionen: number
  gesamtmenge: number | null
  completedAt: string
}

type Phase = "idle" | "processing" | "review" | "frozen"

// ── helpers ──────────────────────────────────────────────────────────────────

function formatSeconds(ms: number | null): string {
  if (ms === null) return ""
  return `${(ms / 1000).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`
}

function fieldValueToString(value: string | number | null): string {
  if (value === null || value === undefined) return ""
  return String(value)
}

function confidenceClass(field: UiField): string {
  if (field.discarded) return "dot-discarded"
  if (field.corrected) return "dot-corrected"
  if (field.confirmed) return "dot-confirmed"
  if (field.confidence >= CONFIDENCE_GREEN) return "dot-green"
  if (field.confidence >= CONFIDENCE_AMBER) return "dot-amber"
  return "dot-red"
}

function isFlagged(field: UiField): boolean {
  if (field.discarded || field.corrected || field.confirmed) return false
  return field.confidence < CONFIDENCE_GREEN || field.handwritten
}

function mapAlternatives(dto: ExtractedFieldDto): UiAlternative[] {
  return (dto.alternatives ?? [])
    .map((alt) => ({
      value: fieldValueToString(alt.value),
      confidence: alt.confidence,
      hint: alt.hint,
    }))
    .filter((alt) => alt.value !== "")
}

function buildFields(extraction: ExtractionDto): Map<string, UiField> {
  const fields = new Map<string, UiField>()
  for (const { name, label } of KOPF_FIELDS) {
    const dto = extraction.kopf[name]
    const value = fieldValueToString(dto.value)
    fields.set(`kopf.${name}`, {
      path: `kopf.${name}`,
      label,
      numeric: false,
      original: value,
      current: value,
      confidence: dto.confidence,
      sourceText: dto.source_text,
      handwritten: dto.handwritten_correction,
      corrected: false,
      confirmed: false,
      discarded: false,
      alternatives: mapAlternatives(dto),
    })
  }
  extraction.positionen.forEach((position, index) => {
    for (const { name, label, numeric } of POSITION_FIELDS) {
      const dto = position[name]
      const value = fieldValueToString(dto.value)
      const path = `positionen.${index}.${name}`
      fields.set(path, {
        path,
        label,
        numeric,
        original: value,
        current: value,
        confidence: dto.confidence,
        sourceText: dto.source_text,
        handwritten: dto.handwritten_correction,
        corrected: false,
        confirmed: false,
        discarded: false,
        alternatives: mapAlternatives(dto),
      })
    }
  })
  return fields
}

function rotatePoint(point: NormPoint, rotation: number): NormPoint {
  switch (((rotation % 360) + 360) % 360) {
    case 90:
      return { x: 1000 - point.y, y: point.x }
    case 180:
      return { x: 1000 - point.x, y: 1000 - point.y }
    case 270:
      return { x: point.y, y: 1000 - point.x }
    default:
      return point
  }
}

function rotateBox(box: NormBox, rotation: number): NormBox {
  const p1 = rotatePoint({ x: box.x1, y: box.y1 }, rotation)
  const p2 = rotatePoint({ x: box.x2, y: box.y2 }, rotation)
  return {
    x1: Math.min(p1.x, p2.x),
    y1: Math.min(p1.y, p2.y),
    x2: Math.max(p1.x, p2.x),
    y2: Math.max(p1.y, p2.y),
  }
}

function deskewRotation(angle: number): number {
  const rounded = Math.round(-angle / 90) * 90
  return ((rounded % 360) + 360) % 360
}

function randomBetween(min: number, max: number, decimals = 0): string {
  const value = min + Math.random() * (max - min)
  return value.toFixed(decimals)
}

async function parseSse(
  response: Response,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error("Streaming wird nicht unterstützt.")
  const decoder = new TextDecoder()
  let buffer = ""
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary = buffer.indexOf("\n\n")
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      let eventName = "message"
      let data = ""
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) eventName = line.slice(7).trim()
        else if (line.startsWith("data: ")) data += line.slice(6)
      }
      if (data) onEvent(eventName, JSON.parse(data))
      boundary = buffer.indexOf("\n\n")
    }
  }
}

// ── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle")
  const [steps, setSteps] = useState<Steps>(IDLE_STEPS)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [fileName, setFileName] = useState<string>("")
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [ocrPages, setOcrPages] = useState<PageLayoutDto[] | null>(null)
  const [result, setResult] = useState<AnalyzeResponseDto | null>(null)
  const [fields, setFields] = useState<Map<string, UiField>>(new Map())
  const [messdaten, setMessdaten] = useState<Record<number, MessDaten>>({})
  const [erstanlieferung, setErstanlieferung] = useState(false)
  const [completed, setCompleted] = useState<CompletedNote[]>([])
  const [modelName, setModelName] = useState<string>("")
  const [modelOptions, setModelOptions] = useState<ModelOptionDto[]>([])
  const [selectedModel, setSelectedModel] = useState<string>("")
  const [selectedEffort, setSelectedEffort] = useState<string>("")
  const [runInfo, setRunInfo] = useState<{ model: string; effort: string | null } | null>(null)
  const [hoveredPath, setHoveredPath] = useState<string | null>(null)
  const [pinnedPath, setPinnedPath] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [zoom, setZoom] = useState(1)
  const [showOcr, setShowOcr] = useState(false)
  const [autoRotate, setAutoRotate] = useState(true)
  const [showCompleted, setShowCompleted] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    fetch("/api/config")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => data && setModelName(data.model ?? ""))
      .catch(() => undefined)
    fetch("/api/models")
      .then((response) => (response.ok ? response.json() : null))
      .then((data: ModelsDto | null) => {
        if (!data || data.models.length === 0) return
        setModelOptions(data.models)
        const fallback = data.models[0].name
        const initialModel =
          data.models.some((option) => option.name === data.defaultModel)
            ? data.defaultModel
            : fallback
        const initialOption = data.models.find((option) => option.name === initialModel)
        setSelectedModel(initialModel)
        setSelectedEffort(
          data.defaultEffort && initialOption?.reasoningEfforts.includes(data.defaultEffort)
            ? data.defaultEffort
            : (initialOption?.reasoningEfforts[0] ?? ""),
        )
      })
      .catch(() => undefined)
  }, [])

  const selectedModelOption = useMemo(
    () => modelOptions.find((option) => option.name === selectedModel) ?? null,
    [modelOptions, selectedModel],
  )

  useEffect(() => {
    const allowed = selectedModelOption?.reasoningEfforts ?? []
    if (!allowed.includes(selectedEffort)) {
      setSelectedEffort(allowed[0] ?? "")
    }
  }, [selectedEffort, selectedModelOption])

  const activePath = pinnedPath ?? hoveredPath

  const referencesByPath = useMemo(() => {
    const map = new Map<string, ReferenceDto>()
    for (const reference of result?.references ?? []) {
      // Ambiguous matches produce several references per path; keep the first for row state.
      if (!map.has(reference.field_path)) map.set(reference.field_path, reference)
    }
    return map
  }, [result])

  const openFlags = useMemo(
    () => [...fields.values()].filter(isFlagged).length,
    [fields],
  )

  const derived = useMemo(() => {
    const positionCount = result?.extraction.positionen.length ?? 0
    let menge = 0
    let mengeKnown = false
    let paletten = 0
    let palettenKnown = false
    for (let index = 0; index < positionCount; index += 1) {
      const mengeField = fields.get(`positionen.${index}.menge`)
      const palettenField = fields.get(`positionen.${index}.paletten`)
      const mengeValue = Number.parseInt(mengeField?.current ?? "", 10)
      const palettenValue = Number.parseInt(palettenField?.current ?? "", 10)
      if (!Number.isNaN(mengeValue)) {
        menge += mengeValue
        mengeKnown = true
      }
      if (!Number.isNaN(palettenValue)) {
        paletten += palettenValue
        palettenKnown = true
      }
    }
    return {
      positionen: positionCount,
      gesamtmenge: mengeKnown ? menge : null,
      paletten: palettenKnown ? paletten : null,
    }
  }, [fields, result])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setPhase("idle")
    setSteps(IDLE_STEPS)
    setErrorMessage(null)
    setFileName("")
    setPdfDoc(null)
    setOcrPages(null)
    setResult(null)
    setFields(new Map())
    setMessdaten({})
    setErstanlieferung(false)
    setHoveredPath(null)
    setPinnedPath(null)
    setCurrentPage(1)
    setZoom(1)
    setShowOcr(false)
    setRunInfo(null)
  }, [])

  const startAnalysis = useCallback(
    async (file: File) => {
      reset()
      setFileName(file.name)
      setPhase("processing")
      setErrorMessage(null)
      setSteps({
        upload: { status: "active", ms: null },
        ocr: { status: "pending", ms: null },
        llm: { status: "pending", ms: null },
      })

      const controller = new AbortController()
      abortRef.current = controller

      // Load the PDF into the client-side viewer immediately.
      const pdfPromise = (async () => {
        const bytes = await file.arrayBuffer()
        const document = await pdfjs.getDocument({ data: bytes }).promise
        setPdfDoc(document)
      })()

      const formData = new FormData()
      formData.append("file", file)
      if (selectedModel) {
        formData.append("model", selectedModel)
        if (selectedModelOption?.supportsReasoningEffort && selectedEffort) {
          formData.append("reasoning_effort", selectedEffort)
        }
      }

      const uploadStart = performance.now()
      try {
        const response = await fetch("/api/analyze/stream", {
          method: "POST",
          body: formData,
          signal: controller.signal,
        })
        if (!response.ok) {
          const detail = await response.json().catch(() => null)
          throw new Error(detail?.detail ?? `HTTP ${response.status}`)
        }
        let failed: string | null = null
        await parseSse(response, (eventName, payload) => {
          const data = payload as Record<string, unknown>
          if (eventName === "started") {
            setSteps((previous) => ({
              ...previous,
              upload: { status: "done", ms: performance.now() - uploadStart },
              ocr: { status: "active", ms: null },
              llm: { status: "active", ms: null },
            }))
          } else if (eventName === "model_started") {
            setRunInfo({
              model: String(data.model ?? ""),
              effort: (data.reasoningEffort as string | null) ?? null,
            })
          } else if (eventName === "layout_completed") {
            setOcrPages(data.pages as PageLayoutDto[])
            setSteps((previous) => ({
              ...previous,
              ocr: { status: "done", ms: (data.durationMs as number) ?? null },
            }))
          } else if (eventName === "model_completed") {
            setSteps((previous) => ({
              ...previous,
              llm: { status: "done", ms: (data.durationMs as number) ?? null },
            }))
          } else if (eventName === "completed") {
            const analyzeResult = payload as AnalyzeResponseDto
            setResult(analyzeResult)
            setFields(buildFields(analyzeResult.extraction))
            setPhase("review")
          } else if (eventName === "error") {
            failed = String(data.detail ?? "Analyse fehlgeschlagen.")
          }
        })
        if (failed) throw new Error(failed)
        await pdfPromise
      } catch (error) {
        if (controller.signal.aborted) return
        setErrorMessage(error instanceof Error ? error.message : String(error))
        setPhase("idle")
        setSteps((previous) => ({
          upload: previous.upload.status === "done" ? previous.upload : { status: "error", ms: null },
          ocr: previous.ocr.status === "done" ? previous.ocr : { status: "error", ms: null },
          llm: previous.llm.status === "done" ? previous.llm : { status: "error", ms: null },
        }))
      }
    },
    [reset, selectedModel, selectedEffort, selectedModelOption],
  )

  const updateField = useCallback((path: string, updater: (field: UiField) => UiField) => {
    setFields((previous) => {
      const next = new Map(previous)
      const field = next.get(path)
      if (field) next.set(path, updater(field))
      return next
    })
  }, [])

  const finalize = useCallback(() => {
    if (!result) return
    const lsField = fields.get("kopf.lieferschein_nummer")
    setCompleted((previous) => [
      {
        fileName: result.file_name,
        lieferscheinNummer: lsField?.current || "—",
        positionen: derived.positionen,
        gesamtmenge: derived.gesamtmenge,
        completedAt: new Date().toLocaleTimeString("de-DE", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      },
      ...previous,
    ])
    setPhase("frozen")
  }, [derived, fields, result])

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-icon" aria-hidden>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none">
              <path
                d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
                stroke="#fff"
                strokeWidth="1.6"
              />
              <path d="m9 13 2.2 2.2L15.5 11" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </span>
          <h1>Lieferschein-Erfassung</h1>
        </div>
        <div className="topbar-right">
          {modelOptions.length > 0 ? (
            <div className="model-picker">
              <label>
                Modell
                <select
                  value={selectedModel}
                  disabled={phase === "processing"}
                  onChange={(event) => setSelectedModel(event.target.value)}
                >
                  {modelOptions.map((option) => (
                    <option key={option.name} value={option.name}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Reasoning
                <select
                  value={selectedModelOption?.supportsReasoningEffort ? selectedEffort : ""}
                  disabled={phase === "processing" || !selectedModelOption?.supportsReasoningEffort}
                  onChange={(event) => setSelectedEffort(event.target.value)}
                >
                  {!selectedModelOption?.supportsReasoningEffort && <option value="">—</option>}
                  {(selectedModelOption?.reasoningEfforts ?? []).map((effort) => (
                    <option key={effort} value={effort}>
                      {EFFORT_LABELS[effort] ?? effort}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            modelName && <span className="model-chip">{modelName}</span>
          )}
          {completed.length > 0 && (
            <div className="completed-wrap">
              <button className="chip-button" onClick={() => setShowCompleted((v) => !v)}>
                Erfasst: {completed.length}
              </button>
              {showCompleted && (
                <div className="completed-dropdown">
                  {completed.map((note, index) => (
                    <div key={index} className="completed-row">
                      <div>
                        <strong>LS {note.lieferscheinNummer}</strong>
                        <span className="completed-file">{note.fileName}</span>
                      </div>
                      <div className="completed-meta">
                        {note.positionen} Pos. · {note.gesamtmenge ?? "—"} Ex. · {note.completedAt}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {phase !== "idle" && (
            <button className="secondary-button" onClick={reset}>
              Neuer Lieferschein
            </button>
          )}
        </div>
      </header>

      {phase === "idle" ? (
        <IdleScreen errorMessage={errorMessage} onStart={startAnalysis} />
      ) : (
        <main className="split">
          <PdfViewer
            pdfDoc={pdfDoc}
            ocrPages={ocrPages}
            references={result?.references ?? []}
            activePath={activePath}
            pinnedPath={pinnedPath}
            currentPage={currentPage}
            zoom={zoom}
            showOcr={showOcr}
            autoRotate={autoRotate}
            fileName={fileName}
            onPageChange={setCurrentPage}
            onZoomChange={setZoom}
            onToggleOcr={() => setShowOcr((v) => !v)}
            onToggleRotate={() => setAutoRotate((v) => !v)}
            onPickReference={(path) => {
              setPinnedPath((previous) => (previous === path ? null : path))
            }}
            onHoverReference={setHoveredPath}
          />
          <section className="pane">
            <ProgressStrip steps={steps} totalMs={result?.timings.total_ms ?? null} runInfo={runInfo} />
            {erstanlieferung && (
              <div className="banner banner-info">
                Erstanlieferung, max. eine Palette in Autostore einlagern.
              </div>
            )}
            {result && result.extraction.hinweise.length > 0 && (
              <div className="banner banner-hints">
                <strong>Hinweise des Modells</strong>
                <ul>
                  {result.extraction.hinweise.map((hint, index) => (
                    <li key={index}>{hint}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="pane-scroll">
              <ExtractionPane
                phase={phase}
                steps={steps}
                result={result}
                fields={fields}
                referencesByPath={referencesByPath}
                activePath={activePath}
                erstanlieferung={erstanlieferung}
                messdaten={messdaten}
                derived={derived}
                onErstanlieferung={setErstanlieferung}
                onMessdaten={(index, data) =>
                  setMessdaten((previous) => ({ ...previous, [index]: data }))
                }
                onHover={setHoveredPath}
                onPin={(path) => {
                  setPinnedPath((previous) => (previous === path ? null : path))
                  const reference = referencesByPath.get(path)
                  if (reference) setCurrentPage(reference.page)
                }}
                onUpdateField={updateField}
              />
            </div>
            <footer className="pane-footer">
              {phase === "frozen" ? (
                <span className="chip chip-done">Erfasst ✓</span>
              ) : phase === "processing" ? (
                <span className="chip">Verarbeitung läuft …</span>
              ) : openFlags > 0 ? (
                <span className="chip chip-warn">
                  ⚠ {openFlags} {openFlags === 1 ? "Feld" : "Felder"} zu prüfen
                </span>
              ) : (
                <span className="chip chip-ok">Alle Felder geprüft</span>
              )}
              {phase === "frozen" ? (
                <button className="primary-button" onClick={reset}>
                  Neuer Lieferschein
                </button>
              ) : (
                <button
                  className="primary-button"
                  disabled={phase !== "review" || openFlags > 0}
                  onClick={finalize}
                  title={openFlags > 0 ? "Bitte zuerst alle markierten Felder prüfen." : undefined}
                >
                  Erfassung abschließen
                </button>
              )}
            </footer>
          </section>
        </main>
      )}
    </div>
  )
}

// ── Idle screen: dropzone + sample gallery ───────────────────────────────────

function IdleScreen({
  errorMessage,
  onStart,
}: {
  errorMessage: string | null
  onStart: (file: File) => void
}) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (file) onStart(file)
  }

  return (
    <main className="idle">
      <div className="idle-inner">
        <h2>Lieferschein hochladen</h2>
        <p className="idle-sub">
          Gescannten Lieferschein (PDF) ablegen. Felder werden per OCR und multimodalem
          LLM extrahiert, mit Fundstellen im Dokument verknüpft und zur Prüfung angezeigt.
        </p>
        {errorMessage && <div className="banner banner-error">{errorMessage}</div>}
        <div
          className={`dropzone${dragging ? " dropzone-active" : ""}`}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setDragging(false)
            handleFiles(event.dataTransfer.files)
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <svg viewBox="0 0 24 24" width="40" height="40" fill="none" aria-hidden>
            <path
              d="M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
              stroke="#0078d4"
              strokeWidth="1.4"
            />
            <path d="M12 17v-6m0 0-2.5 2.5M12 11l2.5 2.5" stroke="#0078d4" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <strong>PDF hierher ziehen</strong>
          <span>oder klicken zum Auswählen</span>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf"
            hidden
            onChange={(event) => handleFiles(event.target.files)}
          />
        </div>
      </div>
    </main>
  )
}

// ── Progress strip with per-step latency ─────────────────────────────────────

function StepChip({
  step,
  label,
  detail,
}: {
  step: StepState
  label: string
  detail?: string | null
}) {
  return (
    <div className={`progress-item progress-${step.status}`}>
      <span className="progress-dot" aria-hidden>
        {step.status === "done" ? "✓" : step.status === "error" ? "✕" : ""}
      </span>
      <span className="progress-label">{label}</span>
      {detail && <span className="progress-model">{detail}</span>}
      {step.ms !== null && <span className="progress-ms">{formatSeconds(step.ms)}</span>}
    </div>
  )
}

function ProgressStrip({
  steps,
  totalMs,
  runInfo,
}: {
  steps: Steps
  totalMs: number | null
  runInfo: { model: string; effort: string | null } | null
}) {
  const llmDetail = runInfo
    ? `${runInfo.model}${runInfo.effort ? ` · ${EFFORT_LABELS[runInfo.effort] ?? runInfo.effort}` : ""}`
    : null
  // OCR and LLM extraction run in parallel on the backend; the fork makes
  // that visible (total ≈ max of both, not the sum).
  return (
    <div className="progress-strip">
      <StepChip step={steps.upload} label="Upload" />
      <svg className="progress-fork" viewBox="0 0 28 44" width="28" height="44" aria-hidden>
        <path d="M0 22 H7 C15 22 15 10 23 10 H28" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M0 22 H7 C15 22 15 34 23 34 H28" fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
      <div className="progress-parallel" title="OCR und LLM-Extraktion laufen parallel">
        <StepChip step={steps.ocr} label="OCR" />
        <StepChip step={steps.llm} label="LLM-Extraktion" detail={llmDetail} />
      </div>
      {totalMs !== null && <span className="progress-total">gesamt {formatSeconds(totalMs)}</span>}
    </div>
  )
}

// ── PDF viewer with overlays ─────────────────────────────────────────────────

function PdfViewer({
  pdfDoc,
  ocrPages,
  references,
  activePath,
  pinnedPath,
  currentPage,
  zoom,
  showOcr,
  autoRotate,
  fileName,
  onPageChange,
  onZoomChange,
  onToggleOcr,
  onToggleRotate,
  onPickReference,
  onHoverReference,
}: {
  pdfDoc: PDFDocumentProxy | null
  ocrPages: PageLayoutDto[] | null
  references: ReferenceDto[]
  activePath: string | null
  pinnedPath: string | null
  currentPage: number
  zoom: number
  showOcr: boolean
  autoRotate: boolean
  fileName: string
  onPageChange: (page: number) => void
  onZoomChange: (zoom: number) => void
  onToggleOcr: () => void
  onToggleRotate: () => void
  onPickReference: (path: string) => void
  onHoverReference: (path: string | null) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [renderSize, setRenderSize] = useState<{ width: number; height: number } | null>(null)

  const pageCount = pdfDoc?.numPages ?? 0
  const ocrPage = ocrPages?.find((page) => page.page === currentPage) ?? null
  const rotation = autoRotate && ocrPage ? deskewRotation(ocrPage.angle) : 0

  useEffect(() => {
    let cancelled = false
    let renderTask: { cancel: () => void } | null = null
    const render = async () => {
      if (!pdfDoc || !canvasRef.current || !containerRef.current) return
      const page = await pdfDoc.getPage(Math.min(currentPage, pdfDoc.numPages))
      if (cancelled) return
      const viewportRotation = ((page.rotate + rotation) % 360 + 360) % 360
      const baseViewport = page.getViewport({ scale: 1, rotation: viewportRotation })
      const available = containerRef.current.clientWidth - 48
      const scale = (available / baseViewport.width) * zoom
      const viewport = page.getViewport({ scale, rotation: viewportRotation })
      const canvas = canvasRef.current
      const context = canvas.getContext("2d")
      if (!context) return
      const ratio = window.devicePixelRatio || 1
      canvas.width = Math.floor(viewport.width * ratio)
      canvas.height = Math.floor(viewport.height * ratio)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`
      const task = page.render({
        canvasContext: context,
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
      })
      renderTask = task
      try {
        await task.promise
        if (!cancelled) setRenderSize({ width: viewport.width, height: viewport.height })
      } catch {
        // render cancelled by a newer render
      }
    }
    void render()
    return () => {
      cancelled = true
      renderTask?.cancel()
    }
  }, [pdfDoc, currentPage, zoom, rotation])

  const pageReferences = references.filter((reference) => reference.page === currentPage)
  const activeReference = pageReferences.find((reference) => reference.field_path === activePath)
  const hasAmbiguous = references.some((reference) => reference.ambiguous)
  // Alternatives (path suffix .altN) only light up while hovered in the picker.
  const visibleReferences = pageReferences.filter(
    (reference) =>
      !/\.alt\d+$/.test(reference.field_path) || reference.field_path === activePath,
  )

  return (
    <section className="viewer">
      <div className="viewer-toolbar">
        <span className="viewer-file" title={fileName}>
          {fileName}
        </span>
        <div className="viewer-controls">
          {pageCount > 1 && (
            <span className="pager">
              <button
                className="icon-button"
                disabled={currentPage <= 1}
                onClick={() => onPageChange(currentPage - 1)}
                aria-label="Vorherige Seite"
              >
                ‹
              </button>
              Seite {currentPage} / {pageCount}
              <button
                className="icon-button"
                disabled={currentPage >= pageCount}
                onClick={() => onPageChange(currentPage + 1)}
                aria-label="Nächste Seite"
              >
                ›
              </button>
            </span>
          )}
          <button className="icon-button" onClick={() => onZoomChange(Math.max(0.5, zoom - 0.25))} aria-label="Verkleinern">
            −
          </button>
          <span className="zoom-label">{Math.round(zoom * 100)} %</span>
          <button className="icon-button" onClick={() => onZoomChange(Math.min(3, zoom + 0.25))} aria-label="Vergrößern">
            +
          </button>
          <button className={`toggle-button${autoRotate ? " toggle-on" : ""}`} onClick={onToggleRotate} disabled={!ocrPage}>
            Begradigen
          </button>
          <button className={`toggle-button${showOcr ? " toggle-on" : ""}`} onClick={onToggleOcr} disabled={!ocrPage}>
            OCR-Overlay
          </button>
        </div>
      </div>
      <div className="viewer-scroll" ref={containerRef}>
        {!pdfDoc && (
          <div className="viewer-loading">
            <div className="shimmer-page" />
          </div>
        )}
        <div className="page-wrap" style={renderSize ? { width: renderSize.width, height: renderSize.height } : undefined}>
          <canvas ref={canvasRef} className="pdf-canvas" />
          {renderSize && (
            <div className="overlay" style={{ width: renderSize.width, height: renderSize.height }}>
              {showOcr &&
                ocrPage?.words.map((word, index) => {
                  const box = rotateBox(word.bbox_norm, rotation)
                  return (
                    <div
                      key={index}
                      className="ocr-box"
                      title={word.text}
                      style={{
                        left: `${box.x1 / 10}%`,
                        top: `${box.y1 / 10}%`,
                        width: `${(box.x2 - box.x1) / 10}%`,
                        height: `${(box.y2 - box.y1) / 10}%`,
                      }}
                    />
                  )
                })}
              {visibleReferences.map((reference, index) => {
                const box = rotateBox(reference.bbox_norm, rotation)
                const isActive = reference.field_path === activePath
                const isPinned = reference.field_path === pinnedPath
                return (
                  <div
                    key={`${reference.field_path}#${index}`}
                    className={`ref-box${reference.ambiguous ? " ref-ambiguous" : ""}${isActive ? " ref-active" : ""}${isPinned ? " ref-pinned" : ""}`}
                    title={
                      reference.ambiguous
                        ? `${reference.region_text} · mehrfach gefunden, Zuordnung unsicher`
                        : reference.region_text
                    }
                    style={{
                      left: `${box.x1 / 10}%`,
                      top: `${box.y1 / 10}%`,
                      width: `${Math.max(box.x2 - box.x1, 6) / 10}%`,
                      height: `${Math.max(box.y2 - box.y1, 6) / 10}%`,
                    }}
                    onMouseEnter={() => onHoverReference(reference.field_path)}
                    onMouseLeave={() => onHoverReference(null)}
                    onClick={() => onPickReference(reference.field_path)}
                  />
                )
              })}
              {activeReference && <div className="ref-glow" aria-hidden />}
            </div>
          )}
        </div>
      </div>
      {hasAmbiguous && (
        <div className="viewer-legend" role="note">
          <span className="legend-item">
            <span className="legend-swatch" aria-hidden />
            Fundstelle
          </span>
          <span className="legend-item">
            <span className="legend-swatch legend-swatch-ambiguous" aria-hidden />
            Mehrfach gefunden – Zuordnung unsicher
          </span>
        </div>
      )}
    </section>
  )
}

// ── Extraction pane ──────────────────────────────────────────────────────────

function ExtractionPane({
  phase,
  steps,
  result,
  fields,
  referencesByPath,
  activePath,
  erstanlieferung,
  messdaten,
  derived,
  onErstanlieferung,
  onMessdaten,
  onHover,
  onPin,
  onUpdateField,
}: {
  phase: Phase
  steps: Steps
  result: AnalyzeResponseDto | null
  fields: Map<string, UiField>
  referencesByPath: Map<string, ReferenceDto>
  activePath: string | null
  erstanlieferung: boolean
  messdaten: Record<number, MessDaten>
  derived: { positionen: number; gesamtmenge: number | null; paletten: number | null }
  onErstanlieferung: (value: boolean) => void
  onMessdaten: (index: number, data: MessDaten) => void
  onHover: (path: string | null) => void
  onPin: (path: string) => void
  onUpdateField: (path: string, updater: (field: UiField) => UiField) => void
}) {
  const frozen = phase === "frozen"

  if (!result) {
    return (
      <div className="pane-body">
        <section className="card">
          <h3>Kopf</h3>
          <div className="kopf-grid">
            {KOPF_FIELDS.map(({ name, label }) => (
              <div key={name} className="kopf-row">
                <span className="field-label">{label}</span>
                <span className={`skeleton${steps.llm.status === "active" ? " shimmer" : ""}`} />
              </div>
            ))}
          </div>
        </section>
        <section className="card">
          <h3>Positionen</h3>
          <div className="position-skeleton">
            <span className={`skeleton${steps.llm.status === "active" ? " shimmer" : ""}`} />
            <span className={`skeleton skeleton-short${steps.llm.status === "active" ? " shimmer" : ""}`} />
          </div>
          <p className="skeleton-hint">
            {steps.ocr.status === "done"
              ? "OCR abgeschlossen – warte auf LLM-Extraktion…"
              : "Dokument wird gelesen…"}
          </p>
        </section>
      </div>
    )
  }

  return (
    <div className="pane-body">
      <section className="card">
        <div className="card-head">
          <h3>Kopf</h3>
          <label className="check-inline">
            <input
              type="checkbox"
              checked={erstanlieferung}
              disabled={frozen}
              onChange={(event) => onErstanlieferung(event.target.checked)}
            />
            Erstanlieferung
          </label>
        </div>
        <div className="kopf-grid">
          {KOPF_FIELDS.map(({ name }) => {
            const field = fields.get(`kopf.${name}`)
            if (!field) return null
            return (
              <FieldRow
                key={name}
                field={field}
                grounded={referencesByPath.has(field.path)}
                active={activePath === field.path}
                frozen={frozen}
                onHover={onHover}
                onPin={onPin}
                onUpdate={onUpdateField}
              />
            )
          })}
        </div>
      </section>

      <section className="card">
        <h3>Positionen</h3>
        {result.extraction.positionen.map((_, index) => (
          <PositionCard
            key={index}
            index={index}
            fields={fields}
            referencesByPath={referencesByPath}
            activePath={activePath}
            frozen={frozen}
            messdaten={messdaten[index] ?? EMPTY_MESSDATEN}
            onMessdaten={(data) => onMessdaten(index, data)}
            onHover={onHover}
            onPin={onPin}
            onUpdate={onUpdateField}
          />
        ))}
        <div className="summary-chips">
          <span className="chip">{derived.positionen} {derived.positionen === 1 ? "Position" : "Positionen"}</span>
          <span className="chip">{derived.gesamtmenge?.toLocaleString("de-DE") ?? "—"} Ex.</span>
          <span className="chip">{derived.paletten ?? "—"} Paletten</span>
        </div>
      </section>
    </div>
  )
}

// ── Single field row with inline edit + confirm ─────────────────────────────

function FieldRow({
  field,
  grounded,
  active,
  frozen,
  compact,
  onHover,
  onPin,
  onUpdate,
}: {
  field: UiField
  grounded: boolean
  active: boolean
  frozen: boolean
  compact?: boolean
  onHover: (path: string | null) => void
  onPin: (path: string) => void
  onUpdate: (path: string, updater: (f: UiField) => UiField) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(field.current)
  const [showAlternatives, setShowAlternatives] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) inputRef.current?.focus()
  }, [editing])

  const commit = () => {
    setEditing(false)
    const value = draft.trim()
    onUpdate(field.path, (previous) => ({
      ...previous,
      current: value,
      corrected: value !== previous.original,
      confirmed: value === previous.original ? true : previous.confirmed,
    }))
  }

  const confirm = () => {
    onUpdate(field.path, (previous) => ({ ...previous, confirmed: true }))
  }

  const discard = () => {
    setEditing(false)
    onUpdate(field.path, (previous) => ({
      ...previous,
      current: "",
      discarded: true,
      confirmed: false,
      corrected: false,
    }))
  }

  const restore = () => {
    onUpdate(field.path, (previous) => ({
      ...previous,
      current: previous.original,
      discarded: false,
    }))
  }

  const applyAlternative = (alternative: UiAlternative) => {
    setShowAlternatives(false)
    setEditing(false)
    onUpdate(field.path, (previous) => ({
      ...previous,
      current: alternative.value,
      corrected: alternative.value !== previous.original,
      confirmed: alternative.value === previous.original ? true : previous.confirmed,
      discarded: false,
    }))
  }

  const flagged = isFlagged(field)
  const hasAlternatives = field.alternatives.length > 0

  return (
    <div
      className={`field-row${active ? " field-active" : ""}${compact ? " field-compact" : ""}`}
      onMouseEnter={() => onHover(field.path)}
      onMouseLeave={() => onHover(null)}
    >
      <span className="field-label">{field.label}</span>
      <div className="field-value-wrap">
        {field.discarded ? (
          <>
            <span
              className="field-value field-discarded"
              title={`Verworfen – Original: ${field.original || "—"}`}
            >
              <span className="field-empty">—</span>
            </span>
            <span className="discarded-badge">verworfen</span>
            {!frozen && (
              <button className="restore-button" title="Wert wiederherstellen" onClick={restore}>
                ↺
              </button>
            )}
          </>
        ) : editing ? (
          <input
            ref={inputRef}
            className="field-input"
            value={draft}
            inputMode={field.numeric ? "numeric" : undefined}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === "Enter") commit()
              if (event.key === "Escape") {
                setDraft(field.current)
                setEditing(false)
              }
            }}
          />
        ) : (
          <button
            className={`field-value${grounded ? " field-grounded" : ""}`}
            disabled={frozen}
            title={
              grounded
                ? field.sourceText
                  ? `Fundstelle: „${field.sourceText}"`
                  : "Fundstelle im Dokument"
                : "keine Fundstelle im Dokument"
            }
            onClick={() => {
              if (grounded) onPin(field.path)
              setDraft(field.current)
              setEditing(true)
            }}
          >
            {field.current || <span className="field-empty">—</span>}
          </button>
        )}
        {field.handwritten && !field.discarded && (
          <span className="hw-badge" title="Handschriftliche Korrektur auf dem Dokument">
            ✍️
          </span>
        )}
        {field.corrected && (
          <span className="corrected-badge" title={`Original: ${field.original || "—"}`}>
            korrigiert
          </span>
        )}
        {!grounded && !editing && !field.discarded && (
          <span className="no-source">keine Fundstelle</span>
        )}
        {flagged && !frozen && (
          <>
            <button className="confirm-button" title="Wert bestätigen" onClick={confirm}>
              ✓
            </button>
            <button className="discard-button" title="Wert verwerfen" onClick={discard}>
              ✕
            </button>
          </>
        )}
        {hasAlternatives && !frozen && (
          <button
            className={`alt-toggle${flagged || showAlternatives ? " alt-toggle-visible" : ""}`}
            title={`${field.alternatives.length} Alternative${field.alternatives.length === 1 ? "" : "n"} vom Modell`}
            onClick={() => setShowAlternatives((value) => !value)}
          >
            {field.alternatives.length} {showAlternatives ? "⌃" : "⌄"}
          </button>
        )}
        <span
          className={`dot ${confidenceClass(field)}`}
          title={
            field.discarded
              ? "Wert verworfen"
              : `Konfidenz ${(field.confidence * 100).toFixed(0)} %`
          }
        />
      </div>
      {showAlternatives && hasAlternatives && !frozen && (
        <div className="alt-panel">
          {field.alternatives.map((alternative, index) => (
            <button
              key={index}
              className="alt-option"
              title="Alternative übernehmen"
              onMouseEnter={() => onHover(`${field.path}.alt${index}`)}
              onMouseLeave={() => onHover(field.path)}
              onClick={() => applyAlternative(alternative)}
            >
              <span className="alt-value">{alternative.value}</span>
              <span className="alt-confidence">
                <span className="alt-bar">
                  <span
                    className="alt-bar-fill"
                    style={{ width: `${Math.round(alternative.confidence * 100)}%` }}
                  />
                </span>
                {Math.round(alternative.confidence * 100)} %
              </span>
              {alternative.hint && <span className="alt-hint">{alternative.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Position card incl. Messdaten + Messtisch ────────────────────────────────

function PositionCard({
  index,
  fields,
  referencesByPath,
  activePath,
  frozen,
  messdaten,
  onMessdaten,
  onHover,
  onPin,
  onUpdate,
}: {
  index: number
  fields: Map<string, UiField>
  referencesByPath: Map<string, ReferenceDto>
  activePath: string | null
  frozen: boolean
  messdaten: MessDaten
  onMessdaten: (data: MessDaten) => void
  onHover: (path: string | null) => void
  onPin: (path: string) => void
  onUpdate: (path: string, updater: (f: UiField) => UiField) => void
}) {
  const [showMess, setShowMess] = useState(false)
  const [showTisch, setShowTisch] = useState(false)

  const positionFields = POSITION_FIELDS.map(({ name }) => fields.get(`positionen.${index}.${name}`)).filter(
    (field): field is UiField => Boolean(field),
  )
  const openCount = positionFields.filter(isFlagged).length

  const set = (patch: Partial<MessDaten>) => onMessdaten({ ...messdaten, ...patch })

  const vpeBerechnen = () => {
    const basis = Number.parseFloat(messdaten.breite) || 210
    const fbS22 = String(Math.max(1, Math.round(600 / basis)))
    const comp1 = String(Math.max(1, Math.round(400 / basis)))
    const comp4 = String(Math.max(1, Math.round(240 / basis)))
    set({
      fbS22,
      comp1,
      comp4,
      fbS22Checked: true,
      comp1Checked: true,
      comp4Checked: true,
      autostore: Boolean(comp1 || comp4),
    })
  }

  return (
    <div className="position-card">
      <div className="position-head">
        <span className="position-number">{index + 1}</span>
        {openCount > 0 && <span className="position-open">{openCount} offen</span>}
        <button className="messtisch-button" disabled={frozen} onClick={() => setShowTisch(true)}>
          ✎ Messtisch
        </button>
      </div>
      <div className="position-grid">
        {POSITION_FIELDS.map(({ name }) => {
          const field = fields.get(`positionen.${index}.${name}`)
          if (!field) return null
          return (
            <FieldRow
              key={name}
              field={field}
              grounded={referencesByPath.has(field.path)}
              active={activePath === field.path}
              frozen={frozen}
              compact
              onHover={onHover}
              onPin={onPin}
              onUpdate={onUpdate}
            />
          )
        })}
      </div>
      <button className="mess-toggle" onClick={() => setShowMess((v) => !v)}>
        {showMess ? "▾" : "▸"} Messdaten
      </button>
      {showMess && (
        <div className="messdaten">
          <div className="mess-group">
            <span className="mess-caption">Artikelmaße (mm) & Gewicht (g)</span>
            <div className="mess-fields">
              <label>
                b
                <input value={messdaten.breite} disabled={frozen} inputMode="decimal" onChange={(e) => set({ breite: e.target.value })} />
              </label>
              <label>
                l
                <input value={messdaten.laenge} disabled={frozen} inputMode="decimal" onChange={(e) => set({ laenge: e.target.value })} />
              </label>
              <label>
                h
                <input value={messdaten.hoehe} disabled={frozen} inputMode="decimal" onChange={(e) => set({ hoehe: e.target.value })} />
              </label>
              <label>
                Gewicht
                <input value={messdaten.gewicht} disabled={frozen} inputMode="decimal" onChange={(e) => set({ gewicht: e.target.value })} />
              </label>
            </div>
          </div>
          <div className="mess-group">
            <span className="mess-caption">Feinwaage (g)</span>
            <div className="mess-fields">
              <label>
                Karton
                <input value={messdaten.kartonGewicht} disabled={frozen} inputMode="decimal" onChange={(e) => set({ kartonGewicht: e.target.value })} />
              </label>
              <label>
                Verbundmaterial
                <input value={messdaten.verbundGewicht} disabled={frozen} inputMode="decimal" onChange={(e) => set({ verbundGewicht: e.target.value })} />
              </label>
              <label>
                Folie
                <input value={messdaten.folieGewicht} disabled={frozen} inputMode="decimal" onChange={(e) => set({ folieGewicht: e.target.value })} />
              </label>
            </div>
          </div>
          <div className="mess-group">
            <span className="mess-caption">Verpackungseinheiten</span>
            <div className="vpe-rows">
              {(
                [
                  ["FB-S22", "fbS22", "fbS22Checked"],
                  ["COMP1", "comp1", "comp1Checked"],
                  ["COMP4", "comp4", "comp4Checked"],
                ] as const
              ).map(([label, valueKey, checkKey]) => (
                <label key={label} className="vpe-row">
                  <input
                    type="checkbox"
                    checked={messdaten[checkKey]}
                    disabled={frozen}
                    onChange={(e) => set({ [checkKey]: e.target.checked } as Partial<MessDaten>)}
                  />
                  <span className="vpe-label">{label}</span>
                  <input
                    className="vpe-value"
                    value={messdaten[valueKey]}
                    disabled={frozen}
                    inputMode="numeric"
                    onChange={(e) => set({ [valueKey]: e.target.value } as Partial<MessDaten>)}
                  />
                </label>
              ))}
              <div className="vpe-actions">
                <button className="secondary-button" disabled={frozen} onClick={vpeBerechnen}>
                  VPE berechnen
                </button>
                <label className="check-inline">
                  <input
                    type="checkbox"
                    checked={messdaten.autostore}
                    disabled={frozen}
                    onChange={(e) => set({ autostore: e.target.checked })}
                  />
                  Autostore-Artikel
                </label>
              </div>
            </div>
          </div>
        </div>
      )}
      {showTisch && (
        <MesstischPopover
          onClose={() => setShowTisch(false)}
          onApply={(values) => {
            set(values)
            setShowMess(true)
            setShowTisch(false)
          }}
        />
      )}
    </div>
  )
}

function MesstischPopover({
  onClose,
  onApply,
}: {
  onClose: () => void
  onApply: (values: Partial<MessDaten>) => void
}) {
  const [values] = useState(() => ({
    breite: randomBetween(105, 240),
    laenge: randomBetween(148, 320),
    hoehe: randomBetween(8, 45),
    gewicht: randomBetween(180, 1450),
    kartonGewicht: randomBetween(20, 80),
    verbundGewicht: randomBetween(4, 28),
    folieGewicht: randomBetween(2, 14),
  }))
  return (
    <div className="popover-backdrop" onClick={onClose}>
      <div className="popover" onClick={(event) => event.stopPropagation()}>
        <h4>Messtisch</h4>
        <p className="popover-sub">Simulierte Werte von Messstation & Waage</p>
        <dl className="popover-values">
          <div>
            <dt>Artikelmaße b×l×h</dt>
            <dd>
              {values.breite} × {values.laenge} × {values.hoehe} mm
            </dd>
          </div>
          <div>
            <dt>Artikelgewicht</dt>
            <dd>{values.gewicht} g</dd>
          </div>
          <div>
            <dt>Karton / Verbund / Folie</dt>
            <dd>
              {values.kartonGewicht} / {values.verbundGewicht} / {values.folieGewicht} g
            </dd>
          </div>
        </dl>
        <div className="popover-actions">
          <button className="secondary-button" onClick={onClose}>
            Abbrechen
          </button>
          <button className="primary-button" onClick={() => onApply(values)}>
            Übernehmen
          </button>
        </div>
      </div>
    </div>
  )
}
