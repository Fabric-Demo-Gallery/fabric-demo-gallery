import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react"

type SampleDrawing = {
  id: string
  title: string
  description: string
  image_path: string
  width: number
  height: number
  expected_focus: string[]
}

type DrawingIdentity = {
  title: string | null
  drawing_number: string | null
  revision: string | null
  material: string | null
  units: string | null
  sheet: string | null
  scale: string | null
}

type Tolerance = {
  plus: number | null
  minus: number | null
  text: string | null
}

type ExtractedDimension = {
  label: string
  value: number | null
  unit: string | null
  type: string | null
  quantity: number | null
  tolerance: Tolerance | null
  feature: string | null
  view: string | null
  confidence: number
  needs_review: boolean
}

type SurfaceFinish = {
  label: string
  type: string | null
  value: number | null
  confidence: number
  needs_review: boolean
}

type GdAndTCallout = {
  label: string
  symbol: string | null
  tolerance: string | null
  datum: string | null
  confidence: number
  needs_review: boolean
}

type DrawingNote = {
  text: string
  category: string | null
  confidence: number
  needs_review: boolean
}

type ReviewFlag = {
  severity: "low" | "medium" | "high"
  message: string
}

type NormalizedPoint = {
  x: number
  y: number
}

type NormalizedBoundingBox = {
  x1: number
  y1: number
  x2: number
  y2: number
}

type SourceRegion = {
  id: string
  text: string
  polygon_norm: NormalizedPoint[]
  bbox_norm: NormalizedBoundingBox
}

type GroundingReference = {
  id: string
  kind: "identity" | "dimension" | "surface_finish" | "gdt" | "note"
  item_index: number
  label: string
  match_score: number
  region: SourceRegion
}

type DrawingAnalysis = {
  summary: string
  identity: DrawingIdentity
  dimensions: ExtractedDimension[]
  surface_finish: SurfaceFinish[]
  gd_and_t: GdAndTCallout[]
  notes: DrawingNote[]
  review_flags: ReviewFlag[]
}

type AnalyzeResponse = {
  sample_id: string | null
  file_name: string
  model: string
  result: DrawingAnalysis
  references: GroundingReference[]
}

type RuntimeConfig = {
  apiBaseUrl: string
}

type ModelConfig = {
  model: string
  hasModelEndpoint: boolean
}

type StreamStage =
  | "idle"
  | "started"
  | "layout_started"
  | "layout_completed"
  | "model_started"
  | "model_completed"
  | "grounding_started"
  | "completed"

type AnalysisProgress = {
  stage: StreamStage
  regionCount: number
}

type Language = "de" | "en"
type DimensionKind = "linear" | "diameter" | "radius" | "angle" | "thread" | "other" | "fallback"
type ProgressStepKey = "prepare" | "layout" | "model" | "grounding" | "result"
type Translation = {
  languageName: string
  languageSelectLabel: string
  heroEyebrow: string
  heroTitle: string
  heroDescription: string
  model: string
  loading: string
  ready: string
  endpointMissing: string
  sampleDrawing: string
  uploadImage: string
  chooseImage: string
  analyzeRunning: string
  analyzeDrawing: string
  emptyDrawing: string
  selectedDrawingAlt: string
  highlightLabel: string
  analysisResult: string
  placeholder: string
  unnamedDrawing: string
  drawingHeader: string
  drawingNumber: string
  revision: string
  material: string
  unit: string
  sheet: string
  scale: string
  dimensions: string
  productionNotes: string
  notes: string
  reviewFlags: string
  unknownView: string
  noReference: string
  source: string
  progressTitle: string
  partialTitle: string
  partialDescription: string
  detectedRegions: string
  skeletonTitleBlock: string
  skeletonDimensions: string
  progressSteps: Record<ProgressStepKey, string>
  errors: {
    config: string
    samples: string
    model: string
    appData: string
    noInput: string
    analysisFailed: string
  }
  dimensionKinds: Record<DimensionKind, string>
  severities: Record<ReviewFlag["severity"], string>
}

const LANGUAGE_STORAGE_KEY = "technical-drawing-analysis-language"

const translations: Record<Language, Translation> = {
  de: {
    languageName: "Deutsch",
    languageSelectLabel: "Sprache auswählen",
    heroEyebrow: "Multimodale Fertigungs-KI",
    heroTitle: "Technische Zeichnungsanalyse",
    heroDescription:
      "Beispielzeichnung auswählen oder ein Bild hochladen, sichtbare Maße und Toleranzen extrahieren und die Quellen direkt in der Zeichnung prüfen.",
    model: "Modell",
    loading: "Lädt...",
    ready: "Bereit zur Analyse",
    endpointMissing: "Endpunkt fehlt",
    sampleDrawing: "Beispielzeichnung",
    uploadImage: "Oder Bild hochladen",
    chooseImage: "Bild auswählen",
    analyzeRunning: "Analyse läuft...",
    analyzeDrawing: "Zeichnung analysieren",
    emptyDrawing: "Zeichnung auswählen oder Bild hochladen.",
    selectedDrawingAlt: "Ausgewählte technische Zeichnung",
    highlightLabel: "Markierung",
    analysisResult: "Prüfergebnis",
    placeholder: "Nach der Analyse erscheinen hier strukturierte Felder und Quellenhinweise.",
    unnamedDrawing: "Unbenannte Zeichnung",
    drawingHeader: "Zeichnungskopf",
    drawingNumber: "Zeichnungsnr.",
    revision: "Revision",
    material: "Material",
    unit: "Einheit",
    sheet: "Blatt",
    scale: "Maßstab",
    dimensions: "Maße",
    productionNotes: "Fertigungshinweise",
    notes: "Notizen",
    reviewFlags: "Prüfhinweise",
    unknownView: "Ansicht unbekannt",
    noReference: "Keine Textquelle zugeordnet",
    source: "Quelle",
    progressTitle: "Analyse läuft",
    partialTitle: "Textregionen erkannt",
    partialDescription: "Quellen werden vorbereitet, die semantische Interpretation folgt.",
    detectedRegions: "erkannte Textregionen",
    skeletonTitleBlock: "Zeichnungskopf wird vorbereitet",
    skeletonDimensions: "Maße werden interpretiert",
    progressSteps: {
      prepare: "Zeichnung vorbereiten",
      layout: "Textregionen erkennen",
      model: "Maße interpretieren",
      grounding: "Quellen zuordnen",
      result: "Prüfergebnis erstellen",
    },
    errors: {
      config: "Frontend-Konfiguration konnte nicht geladen werden.",
      samples: "Beispielzeichnungen konnten nicht geladen werden.",
      model: "Modellkonfiguration konnte nicht geladen werden.",
      appData: "Anwendungsdaten konnten nicht geladen werden.",
      noInput: "Bitte eine Beispielzeichnung auswählen oder ein Bild hochladen.",
      analysisFailed: "Zeichnungsanalyse fehlgeschlagen.",
    },
    dimensionKinds: {
      linear: "linear",
      diameter: "Durchmesser",
      radius: "Radius",
      angle: "Winkel",
      thread: "Gewinde",
      other: "Sonstiges",
      fallback: "Maß",
    },
    severities: {
      low: "niedrig",
      medium: "mittel",
      high: "hoch",
    },
  },
  en: {
    languageName: "English",
    languageSelectLabel: "Select language",
    heroEyebrow: "Multimodal manufacturing AI",
    heroTitle: "Technical drawing analysis",
    heroDescription:
      "Select a sample drawing or upload an image, extract visible dimensions and tolerances, and verify the sources directly in the drawing.",
    model: "Model",
    loading: "Loading...",
    ready: "Ready to analyze",
    endpointMissing: "Endpoint missing",
    sampleDrawing: "Sample drawing",
    uploadImage: "Or upload an image",
    chooseImage: "Choose image",
    analyzeRunning: "Analyzing...",
    analyzeDrawing: "Analyze drawing",
    emptyDrawing: "Select a drawing or upload an image.",
    selectedDrawingAlt: "Selected technical drawing",
    highlightLabel: "Highlight",
    analysisResult: "Analysis result",
    placeholder: "Structured fields and source references appear here after analysis.",
    unnamedDrawing: "Untitled drawing",
    drawingHeader: "Title block",
    drawingNumber: "Drawing no.",
    revision: "Revision",
    material: "Material",
    unit: "Unit",
    sheet: "Sheet",
    scale: "Scale",
    dimensions: "Dimensions",
    productionNotes: "Manufacturing notes",
    notes: "Notes",
    reviewFlags: "Review flags",
    unknownView: "Unknown view",
    noReference: "No text source assigned",
    source: "Source",
    progressTitle: "Analysis running",
    partialTitle: "Text regions detected",
    partialDescription: "Sources are being prepared; semantic interpretation follows.",
    detectedRegions: "detected text regions",
    skeletonTitleBlock: "Preparing title block",
    skeletonDimensions: "Interpreting dimensions",
    progressSteps: {
      prepare: "Prepare drawing",
      layout: "Detect text regions",
      model: "Interpret dimensions",
      grounding: "Assign sources",
      result: "Create review result",
    },
    errors: {
      config: "Could not load frontend configuration.",
      samples: "Could not load sample drawings.",
      model: "Could not load model configuration.",
      appData: "Could not load application data.",
      noInput: "Select a sample drawing or upload an image.",
      analysisFailed: "Drawing analysis failed.",
    },
    dimensionKinds: {
      linear: "linear",
      diameter: "diameter",
      radius: "radius",
      angle: "angle",
      thread: "thread",
      other: "other",
      fallback: "dimension",
    },
    severities: {
      low: "low",
      medium: "medium",
      high: "high",
    },
  },
}

function initialLanguage(): Language {
  const storedLanguage = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return storedLanguage === "en" ? "en" : "de"
}

function formatPercent(value: number, language: Language): string {
  return new Intl.NumberFormat(language, {
    maximumFractionDigits: 0,
    style: "percent",
  }).format(value)
}

function formatValue(value: string | number | null): string {
  if (value === null || value === "") {
    return "-"
  }
  return String(value)
}

function dimensionKind(value: string | null, text: Translation): string {
  return value ? (text.dimensionKinds[value as DimensionKind] ?? value) : text.dimensionKinds.fallback
}

function polygonPoints(region: SourceRegion): string {
  return region.polygon_norm.map((point) => `${point.x},${point.y}`).join(" ")
}

function progressStepState(step: ProgressStepKey, stage: StreamStage): "pending" | "active" | "done" {
  const order: ProgressStepKey[] = ["prepare", "layout", "model", "grounding", "result"]
  const stageOrder: Record<StreamStage, number> = {
    idle: -1,
    started: 0,
    layout_started: 1,
    layout_completed: 2,
    model_started: 2,
    model_completed: 3,
    grounding_started: 3,
    completed: 5,
  }
  const current = stageOrder[stage]
  const index = order.indexOf(step)
  if (current > index) {
    return "done"
  }
  if (current === index) {
    return "active"
  }
  return "pending"
}

function parseSseMessage(raw: string): { event: string; data: unknown } | null {
  const lines = raw.split("\n")
  const eventLine = lines.find((line) => line.startsWith("event:"))
  const dataLine = lines.find((line) => line.startsWith("data:"))
  if (!eventLine || !dataLine) {
    return null
  }
  return {
    event: eventLine.slice("event:".length).trim(),
    data: JSON.parse(dataLine.slice("data:".length).trim()) as unknown,
  }
}

function App() {
  const [language, setLanguage] = useState<Language>(initialLanguage)
  const [apiBase, setApiBase] = useState("")
  const [samples, setSamples] = useState<SampleDrawing[]>([])
  const [selectedSampleId, setSelectedSampleId] = useState<string>("")
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [uploadPreviewUrl, setUploadPreviewUrl] = useState<string | null>(null)
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null)
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null)
  const [activeReferenceId, setActiveReferenceId] = useState<string | null>(null)
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null)
  const [partialRegions, setPartialRegions] = useState<SourceRegion[]>([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const text = translations[language]

  const selectedSample = useMemo(
    () => samples.find((sample) => sample.id === selectedSampleId) ?? null,
    [samples, selectedSampleId],
  )

  const drawingUrl = uploadedFile
    ? uploadPreviewUrl
    : selectedSample
      ? `${apiBase}/api/samples/${selectedSample.id}/image`
      : null

  useEffect(() => {
    document.documentElement.lang = language
    document.title = translations[language].heroTitle
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
    void loadInitialData(language)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language])

  useEffect(() => {
    return () => {
      if (uploadPreviewUrl) {
        URL.revokeObjectURL(uploadPreviewUrl)
      }
    }
  }, [uploadPreviewUrl])

  async function loadInitialData(nextLanguage: Language): Promise<void> {
    const nextText = translations[nextLanguage]
    try {
      setLoading(true)
      const configResponse = await fetch("/config.json")
      if (!configResponse.ok) {
        throw new Error(nextText.errors.config)
      }
      const runtimeConfig = (await configResponse.json()) as RuntimeConfig
      setApiBase(runtimeConfig.apiBaseUrl)

      const [samplesResponse, modelResponse] = await Promise.all([
        fetch(`${runtimeConfig.apiBaseUrl}/api/samples?language=${nextLanguage}`),
        fetch(`${runtimeConfig.apiBaseUrl}/api/config`),
      ])
      if (!samplesResponse.ok) {
        throw new Error(nextText.errors.samples)
      }
      if (!modelResponse.ok) {
        throw new Error(nextText.errors.model)
      }
      const loadedSamples = (await samplesResponse.json()) as SampleDrawing[]
      setSamples(loadedSamples)
      setSelectedSampleId((current) =>
        loadedSamples.some((sample) => sample.id === current) ? current : (loadedSamples[0]?.id ?? ""),
      )
      setModelConfig((await modelResponse.json()) as ModelConfig)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : nextText.errors.appData)
    } finally {
      setLoading(false)
    }
  }

  function handleLanguageChange(nextLanguage: Language): void {
    if (nextLanguage === language) {
      return
    }
    setLanguage(nextLanguage)
    setAnalysis(null)
    setActiveReferenceId(null)
    setAnalysisProgress(null)
    setPartialRegions([])
    setError(null)
  }

  function handleSampleChange(event: ChangeEvent<HTMLSelectElement>): void {
    setUploadedFile(null)
    if (uploadPreviewUrl) {
      URL.revokeObjectURL(uploadPreviewUrl)
      setUploadPreviewUrl(null)
    }
    setSelectedSampleId(event.target.value)
    setAnalysis(null)
    setActiveReferenceId(null)
    setAnalysisProgress(null)
    setPartialRegions([])
    setError(null)
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0] ?? null
    setAnalysis(null)
    setActiveReferenceId(null)
    setAnalysisProgress(null)
    setPartialRegions([])
    setError(null)
    if (uploadPreviewUrl) {
      URL.revokeObjectURL(uploadPreviewUrl)
      setUploadPreviewUrl(null)
    }
    if (!file) {
      setUploadedFile(null)
      return
    }
    setUploadedFile(file)
    setUploadPreviewUrl(URL.createObjectURL(file))
  }

  async function analyzeDrawing(event: FormEvent): Promise<void> {
    event.preventDefault()
    try {
      setAnalyzing(true)
      setError(null)
      setActiveReferenceId(null)
      setAnalysis(null)
      setPartialRegions([])
      setAnalysisProgress({ stage: "started", regionCount: 0 })
      const body = new FormData()
      if (uploadedFile) {
        body.append("file", uploadedFile)
      } else if (selectedSampleId) {
        body.append("sample_id", selectedSampleId)
      } else {
        throw new Error(text.errors.noInput)
      }
      body.append("language", language)
      const response = await fetch(`${apiBase}/api/analyze/stream`, {
        method: "POST",
        body,
      })
      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(detail?.detail ?? text.errors.analysisFailed)
      }
      if (!response.body) {
        throw new Error(text.errors.analysisFailed)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      let completed = false
      while (true) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const messages = buffer.split("\n\n")
        buffer = messages.pop() ?? ""
        for (const message of messages) {
          const parsed = parseSseMessage(message)
          if (!parsed) {
            continue
          }
          if (parsed.event === "error") {
            const data = parsed.data as { detail?: string }
            throw new Error(data.detail ?? text.errors.analysisFailed)
          }
          if (parsed.event === "layout_completed") {
            const data = parsed.data as { regionCount?: number; regions?: SourceRegion[] }
            setPartialRegions(data.regions ?? [])
            setAnalysisProgress({ stage: "layout_completed", regionCount: data.regionCount ?? 0 })
            continue
          }
          if (parsed.event === "completed") {
            const nextAnalysis = parsed.data as AnalyzeResponse
            setAnalysis(nextAnalysis)
            setActiveReferenceId(nextAnalysis.references[0]?.id ?? null)
            setAnalysisProgress({ stage: "completed", regionCount: nextAnalysis.references.length })
            completed = true
            continue
          }
          setAnalysisProgress((current) => ({
            stage: parsed.event as StreamStage,
            regionCount: current?.regionCount ?? 0,
          }))
        }
      }
      if (!completed) {
        throw new Error(text.errors.analysisFailed)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : text.errors.analysisFailed)
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">{text.heroEyebrow}</p>
          <h1>{text.heroTitle}</h1>
          <p>{text.heroDescription}</p>
        </div>
        <div className="hero-side">
          <div className="language-switch" aria-label={text.languageSelectLabel}>
            {(["de", "en"] as const).map((item) => (
              <button
                aria-pressed={language === item}
                className={language === item ? "active" : ""}
                key={item}
                onClick={() => handleLanguageChange(item)}
                type="button"
              >
                {translations[item].languageName}
              </button>
            ))}
          </div>
          <div className="model-card">
            <span>{text.model}</span>
            <strong>{modelConfig?.model ?? text.loading}</strong>
            <small>{modelConfig?.hasModelEndpoint ? text.ready : text.endpointMissing}</small>
          </div>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="workspace">
        <form className="controls" onSubmit={(event) => void analyzeDrawing(event)}>
          <label>
            {text.sampleDrawing}
            <select value={selectedSampleId} onChange={handleSampleChange} disabled={loading}>
              {samples.map((sample) => (
                <option value={sample.id} key={sample.id}>
                  {sample.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            {text.uploadImage}
            <span className="file-picker">
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={handleUpload} />
              <span>{uploadedFile ? uploadedFile.name : text.chooseImage}</span>
            </span>
          </label>
          {selectedSample && !uploadedFile && (
            <div className="sample-description">
              <strong>{selectedSample.title}</strong>
              <p>{selectedSample.description}</p>
              <div>
                {selectedSample.expected_focus.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
          )}
          <button type="submit" disabled={loading || analyzing || (!selectedSampleId && !uploadedFile)}>
            {analyzing ? text.analyzeRunning : text.analyzeDrawing}
          </button>
        </form>

        <DrawingPanel
          drawingUrl={drawingUrl}
          detectedRegions={partialRegions}
          references={analysis?.references ?? []}
          activeReferenceId={activeReferenceId}
          onSelectReference={setActiveReferenceId}
          text={text}
        />

        <AnalysisPanel
          analysis={analysis}
          activeReferenceId={activeReferenceId}
          analyzing={analyzing}
          partialRegions={partialRegions}
          progress={analysisProgress}
          language={language}
          onSelectReference={setActiveReferenceId}
          text={text}
        />
      </section>
    </main>
  )
}

function DrawingPanel({
  drawingUrl,
  detectedRegions,
  references,
  activeReferenceId,
  onSelectReference,
  text,
}: {
  drawingUrl: string | null
  detectedRegions: SourceRegion[]
  references: GroundingReference[]
  activeReferenceId: string | null
  onSelectReference: (id: string) => void
  text: Translation
}) {
  if (!drawingUrl) {
    return (
      <div className="drawing-panel">
        <div className="empty">{text.emptyDrawing}</div>
      </div>
    )
  }

  return (
    <div className="drawing-panel">
      <div className="drawing-canvas">
        <img src={drawingUrl} alt={text.selectedDrawingAlt} />
        {references.length === 0 && detectedRegions.length > 0 && (
          <svg className="reference-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none">
            {detectedRegions.map((region) => (
              <polygon
                key={region.id}
                className="reference-region detected"
                points={polygonPoints(region)}
              />
            ))}
          </svg>
        )}
        {references.length > 0 && (
          <svg className="reference-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none">
            {references.map((reference) => (
              <polygon
                key={reference.id}
                className={`reference-region ${reference.id === activeReferenceId ? "active" : ""}`}
                points={polygonPoints(reference.region)}
                role="button"
                aria-label={`${text.highlightLabel} ${reference.label}`}
                onMouseEnter={() => onSelectReference(reference.id)}
                onClick={() => onSelectReference(reference.id)}
              />
            ))}
          </svg>
        )}
      </div>
    </div>
  )
}

function ProcessingPanel({
  partialRegions,
  progress,
  text,
}: {
  partialRegions: SourceRegion[]
  progress: AnalysisProgress | null
  text: Translation
}) {
  const stage = progress?.stage ?? "started"
  const steps: ProgressStepKey[] = ["prepare", "layout", "model", "grounding", "result"]
  return (
    <aside className="analysis-panel processing-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{text.analysisResult}</p>
          <h2>{text.progressTitle}</h2>
        </div>
        <span className="model-pill">Live</span>
      </div>
      <ol className="progress-steps">
        {steps.map((step) => {
          const state = progressStepState(step, stage)
          return (
            <li className={state} key={step}>
              <span aria-hidden="true" />
              <div>
                <strong>{text.progressSteps[step]}</strong>
              </div>
            </li>
          )
        })}
      </ol>

      {partialRegions.length > 0 && (
        <section className="partial-regions">
          <h3>{text.partialTitle}</h3>
          <p>{text.partialDescription}</p>
          <strong>
            {partialRegions.length} {text.detectedRegions}
          </strong>
          <div className="region-list">
            {partialRegions.slice(0, 8).map((region) => (
              <span key={region.id}>{region.text}</span>
            ))}
          </div>
        </section>
      )}

      <section>
        <h3>{text.skeletonTitleBlock}</h3>
        <div className="skeleton-grid">
          <span />
          <span />
          <span />
          <span />
        </div>
      </section>
      <section>
        <h3>{text.skeletonDimensions}</h3>
        <div className="skeleton-card" />
        <div className="skeleton-card short" />
        <div className="skeleton-card" />
      </section>
    </aside>
  )
}

function AnalysisPanel({
  analysis,
  activeReferenceId,
  analyzing,
  partialRegions,
  progress,
  language,
  onSelectReference,
  text,
}: {
  analysis: AnalyzeResponse | null
  activeReferenceId: string | null
  analyzing: boolean
  partialRegions: SourceRegion[]
  progress: AnalysisProgress | null
  language: Language
  onSelectReference: (id: string) => void
  text: Translation
}) {
  // When a region is hovered on the drawing, bring the matching panel item into view.
  useEffect(() => {
    if (!activeReferenceId) {
      return
    }
    document
      .querySelector(`[data-reference-id="${activeReferenceId}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [activeReferenceId])

  if (!analysis) {
    if (analyzing || progress) {
      return <ProcessingPanel partialRegions={partialRegions} progress={progress} text={text} />
    }
    return (
      <aside className="analysis-panel placeholder">
        <h2>{text.analysisResult}</h2>
        <p>{text.placeholder}</p>
      </aside>
    )
  }

  const result = analysis.result
  const referencesByKey = new Map(
    analysis.references.map((reference) => [`${reference.kind}-${reference.item_index}`, reference]),
  )
  const titleReference = referencesByKey.get("identity-0")

  function referenceCardClass(reference: GroundingReference | undefined, review: boolean): string {
    const classes = ["card", "reference-card"]
    if (review) {
      classes.push("review")
    }
    if (reference?.id === activeReferenceId) {
      classes.push("active")
    }
    if (!reference) {
      classes.push("no-reference")
    }
    return classes.join(" ")
  }

  function referenceHint(reference: GroundingReference | undefined): string {
    if (!reference) {
      return text.noReference
    }
    return `${text.source}: "${reference.region.text}" · ${formatPercent(reference.match_score, language)}`
  }

  return (
    <aside className="analysis-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{text.analysisResult}</p>
          <h2
            className={
              titleReference
                ? `grounded-title${titleReference.id === activeReferenceId ? " active" : ""}`
                : undefined
            }
            data-reference-id={titleReference?.id}
            onClick={() => titleReference && onSelectReference(titleReference.id)}
            onMouseEnter={() => titleReference && onSelectReference(titleReference.id)}
          >
            {result.identity.title ?? text.unnamedDrawing}
          </h2>
        </div>
        <span className="model-pill">{analysis.model}</span>
      </div>
      <p className="summary">{result.summary}</p>

      <section>
        <h3>{text.drawingHeader}</h3>
        <dl className="identity-grid">
          {/* Indices match the backend identity grounding order (0 = title, shown in the heading). */}
          {[
            { label: text.drawingNumber, value: result.identity.drawing_number, index: 1 },
            { label: text.revision, value: result.identity.revision, index: 2 },
            { label: text.material, value: result.identity.material, index: 3 },
            { label: text.unit, value: result.identity.units, index: 4 },
            { label: text.sheet, value: result.identity.sheet, index: 5 },
            { label: text.scale, value: result.identity.scale, index: 6 },
          ].map((field) => {
            const reference = referencesByKey.get(`identity-${field.index}`)
            return (
              <div
                key={field.label}
                data-reference-id={reference?.id}
                className={reference ? `grounded${reference.id === activeReferenceId ? " active" : ""}` : undefined}
                onClick={() => reference && onSelectReference(reference.id)}
                onMouseEnter={() => reference && onSelectReference(reference.id)}
              >
                <dt>{field.label}</dt>
                <dd>{formatValue(field.value)}</dd>
              </div>
            )
          })}
        </dl>
      </section>

      <section>
        <h3>{text.dimensions}</h3>
        <div className="cards">
          {result.dimensions.map((dimension, index) => {
            const reference = referencesByKey.get(`dimension-${index}`)
            return (
            <div
              className={referenceCardClass(reference, dimension.needs_review)}
              data-reference-id={reference?.id}
              key={dimension.label}
              role="button"
              tabIndex={0}
              onClick={() => reference && onSelectReference(reference.id)}
              onMouseEnter={() => reference && onSelectReference(reference.id)}
              onFocus={() => reference && onSelectReference(reference.id)}
            >
              <div>
                <strong>{dimension.label}</strong>
                <span>{formatPercent(dimension.confidence, language)}</span>
              </div>
              <p>{dimension.feature ?? dimensionKind(dimension.type, text)}</p>
              <small>
                {dimensionKind(dimension.type, text)} · {dimension.view ?? text.unknownView}
              </small>
              <em>{referenceHint(reference)}</em>
            </div>
          )})}
        </div>
      </section>

      {(result.surface_finish.length > 0 || result.gd_and_t.length > 0) && (
        <section>
          <h3>{text.productionNotes}</h3>
          <div className="cards compact">
            {result.surface_finish.map((item, index) => {
              const reference = referencesByKey.get(`surface_finish-${index}`)
              return (
              <div
                className={referenceCardClass(reference, item.needs_review)}
                data-reference-id={reference?.id}
                key={item.label}
                role="button"
                tabIndex={0}
                onClick={() => reference && onSelectReference(reference.id)}
                onMouseEnter={() => reference && onSelectReference(reference.id)}
                onFocus={() => reference && onSelectReference(reference.id)}
              >
                <strong>{item.label}</strong>
                <small>{formatPercent(item.confidence, language)}</small>
                <em>{referenceHint(reference)}</em>
              </div>
            )})}
            {result.gd_and_t.map((item, index) => {
              const reference = referencesByKey.get(`gdt-${index}`)
              return (
              <div
                className={referenceCardClass(reference, item.needs_review)}
                data-reference-id={reference?.id}
                key={item.label}
                role="button"
                tabIndex={0}
                onClick={() => reference && onSelectReference(reference.id)}
                onMouseEnter={() => reference && onSelectReference(reference.id)}
                onFocus={() => reference && onSelectReference(reference.id)}
              >
                <strong>{item.label}</strong>
                <small>{formatPercent(item.confidence, language)}</small>
                <em>{referenceHint(reference)}</em>
              </div>
            )})}
          </div>
        </section>
      )}

      {result.notes.length > 0 && (
        <section>
          <h3>{text.notes}</h3>
          <ul className="notes">
            {result.notes.map((note, index) => {
              const reference = referencesByKey.get(`note-${index}`)
              return (
              <li
                className={reference?.id === activeReferenceId ? "active" : ""}
                data-reference-id={reference?.id}
                key={note.text}
                role="button"
                tabIndex={0}
                onClick={() => reference && onSelectReference(reference.id)}
                onMouseEnter={() => reference && onSelectReference(reference.id)}
                onFocus={() => reference && onSelectReference(reference.id)}
              >
                {note.text}
                <span>{formatPercent(note.confidence, language)}</span>
              </li>
            )})}
          </ul>
        </section>
      )}

      {result.review_flags.length > 0 && (
        <section>
          <h3>{text.reviewFlags}</h3>
          <ul className="flags">
            {result.review_flags.map((flag) => (
              <li className={flag.severity} key={flag.message}>
                <strong>{text.severities[flag.severity]}</strong>
                {flag.message}
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  )
}

export default App
