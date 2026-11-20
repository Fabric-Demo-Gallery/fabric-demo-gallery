import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from delivery_note_extraction.catalog import list_model_options
from delivery_note_extraction.catalog import resolve_reasoning_effort
from delivery_note_extraction.grounding import match_references
from delivery_note_extraction.layout import analyze_layout
from delivery_note_extraction.llm import extract_delivery_note
from delivery_note_extraction.models import AnalyzeResponse
from delivery_note_extraction.models import GroundingRegion
from delivery_note_extraction.models import PageLayout
from delivery_note_extraction.models import Timings
from delivery_note_extraction.models import derive_values
from delivery_note_extraction.pdf import render_pdf_pages
from delivery_note_extraction.settings import get_settings
from delivery_note_extraction.telemetry import agent_span
from delivery_note_extraction.telemetry import instrument_app
from delivery_note_extraction.telemetry import setup_telemetry

setup_telemetry()


def _cors_origins() -> list[str]:
    raw = get_settings().cors_allowed_origins
    if raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="Delivery Note Extraction", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument_app(app)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config_status() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "model": settings.azure_foundry_model,
        "hasModelEndpoint": bool(
            settings.azure_foundry_model
            and (settings.azure_ai_project_endpoint or settings.azure_openai_endpoint)
        ),
    }


@app.get("/api/models")
def list_models() -> dict[str, object]:
    settings = get_settings()
    try:
        options = list_model_options()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    default_effort = (
        resolve_reasoning_effort(settings.azure_foundry_model, None)
        if settings.azure_foundry_model
        else None
    )
    return {
        "models": [
            {
                "name": option.name,
                "model": option.model,
                "supportsReasoningEffort": option.supports_reasoning_effort,
                "reasoningEfforts": list(option.reasoning_efforts),
            }
            for option in options
        ],
        "defaultModel": settings.azure_foundry_model,
        "defaultEffort": default_effort,
    }


def _resolve_model(model: str | None, reasoning_effort: str | None) -> tuple[str, str | None]:
    """Validate the requested model/effort and apply configured defaults."""
    model_name = (model or "").strip() or get_settings().azure_foundry_model
    if not model_name:
        raise HTTPException(status_code=502, detail="AZURE_FOUNDRY_MODEL must be configured.")
    try:
        effort = resolve_reasoning_effort(model_name, reasoning_effort)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return model_name, effort


async def _load_input(file: UploadFile) -> tuple[bytes, str]:
    file_name = file.filename or "upload.pdf"
    is_pdf = (file.content_type or "") == "application/pdf" or file_name.lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=415, detail="Nur PDF-Dateien werden unterstützt.")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(pdf_bytes) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="Datei ist zu groß.")
    return pdf_bytes, file_name


def _elapsed_ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    reasoning_effort: str | None = Form(None),
) -> AnalyzeResponse:
    model_name, effort = _resolve_model(model, reasoning_effort)
    pdf_bytes, file_name = await _load_input(file)
    try:
        with agent_span("analyze_delivery_note"):
            total_start = time.perf_counter()

            async def timed_layout() -> tuple[tuple[list[PageLayout], list[GroundingRegion]], int]:
                start = time.perf_counter()
                result = await analyze_layout(pdf_bytes)
                return result, _elapsed_ms(start)

            layout_task = asyncio.create_task(timed_layout())
            page_images = await asyncio.to_thread(
                render_pdf_pages, pdf_bytes, get_settings().max_llm_pages
            )
            extraction = await extract_delivery_note(
                page_images=page_images,
                file_name=file_name,
                model=model_name,
                reasoning_effort=effort,
            )
            llm_ms = _elapsed_ms(total_start)
            (pages, line_regions), ocr_ms = await layout_task
            grounding_start = time.perf_counter()
            references = match_references(extraction, pages, line_regions)
            return AnalyzeResponse(
                file_name=file_name,
                model=model_name,
                reasoning_effort=effort,
                pages=pages,
                extraction=extraction,
                derived=derive_values(extraction),
                references=references,
                timings=Timings(
                    ocr_ms=ocr_ms,
                    llm_ms=llm_ms,
                    grounding_ms=_elapsed_ms(grounding_start),
                    total_ms=_elapsed_ms(total_start),
                ),
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/analyze/stream")
async def analyze_stream(
    file: UploadFile = File(...),
    model: str | None = Form(None),
    reasoning_effort: str | None = Form(None),
) -> StreamingResponse:
    model_name, effort = _resolve_model(model, reasoning_effort)
    pdf_bytes, file_name = await _load_input(file)

    async def events() -> AsyncIterator[str]:
        try:
            yield _sse("started", {"fileName": file_name})
            with agent_span("analyze_delivery_note"):
                total_start = time.perf_counter()
                layout_start = time.perf_counter()
                layout_task = asyncio.create_task(analyze_layout(pdf_bytes))
                yield _sse("layout_started", {})

                model_start = time.perf_counter()
                yield _sse("model_started", {"model": model_name, "reasoningEffort": effort})
                page_images = await asyncio.to_thread(
                    render_pdf_pages, pdf_bytes, get_settings().max_llm_pages
                )
                model_task = asyncio.create_task(
                    extract_delivery_note(
                        page_images=page_images,
                        file_name=file_name,
                        model=model_name,
                        reasoning_effort=effort,
                    )
                )

                pages = None
                line_regions = None
                extraction = None
                ocr_ms: int | None = None
                llm_ms: int | None = None
                pending: set[asyncio.Task[object]] = {layout_task, model_task}
                while pending:
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        if task is layout_task:
                            pages, line_regions = layout_task.result()
                            ocr_ms = _elapsed_ms(layout_start)
                            yield _sse(
                                "layout_completed",
                                {
                                    "durationMs": ocr_ms,
                                    "pages": [page.model_dump(mode="json") for page in pages],
                                },
                            )
                        elif task is model_task:
                            extraction = model_task.result()
                            llm_ms = _elapsed_ms(model_start)
                            yield _sse("model_completed", {"durationMs": llm_ms})

                if pages is None or line_regions is None or extraction is None:
                    raise RuntimeError("analysis did not complete")

                yield _sse("grounding_started", {})
                grounding_start = time.perf_counter()
                references = match_references(extraction, pages, line_regions)
                grounding_ms = _elapsed_ms(grounding_start)

            response = AnalyzeResponse(
                file_name=file_name,
                model=model_name,
                reasoning_effort=effort,
                pages=pages,
                extraction=extraction,
                derived=derive_values(extraction),
                references=references,
                timings=Timings(
                    ocr_ms=ocr_ms,
                    llm_ms=llm_ms,
                    grounding_ms=grounding_ms,
                    total_ms=_elapsed_ms(total_start),
                ),
            )
            yield _sse("completed", response.model_dump(mode="json"))
        except Exception as exc:  # surface the failure to the client, then end the stream
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")
