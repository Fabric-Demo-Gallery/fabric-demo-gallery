import asyncio
import json
from pathlib import Path
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse

from technical_drawing_analysis.grounding import analyze_layout_regions
from technical_drawing_analysis.grounding import match_references
from technical_drawing_analysis.llm import analyze_drawing
from technical_drawing_analysis.models import AnalyzeResponse
from technical_drawing_analysis.models import Language
from technical_drawing_analysis.models import SampleDrawing
from technical_drawing_analysis.samples import get_sample
from technical_drawing_analysis.samples import list_samples
from technical_drawing_analysis.samples import sample_image_path
from technical_drawing_analysis.settings import get_settings
from technical_drawing_analysis.telemetry import agent_span
from technical_drawing_analysis.telemetry import setup_telemetry


setup_telemetry()


SUPPORTED_MEDIA_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _cors_origins() -> list[str]:
    raw = get_settings().cors_allowed_origins
    if raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _language(value: str | None) -> Language:
    normalized = (value or "de").strip().lower()
    if normalized in {"de", "de-de"}:
        return "de"
    if normalized in {"en", "en-us", "en-gb"}:
        return "en"
    raise HTTPException(status_code=400, detail="unsupported language")


app = FastAPI(title="Technical Drawing Analysis", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
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


@app.get("/api/samples", response_model=list[SampleDrawing])
def samples(language: str = Query(default="de")) -> list[SampleDrawing]:
    return list_samples(_language(language))


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str) -> FileResponse:
    try:
        sample = get_sample(sample_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="sample not found") from exc
    path = sample_image_path(sample)
    if not path.exists():
        raise HTTPException(status_code=404, detail="sample image not found")
    return FileResponse(path, media_type="image/png", filename=path.name)


def _media_type_for_path(path: Path) -> str:
    if path.suffix.lower() == ".png":
        return "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if path.suffix.lower() == ".webp":
        return "image/webp"
    raise HTTPException(status_code=415, detail="unsupported sample image type")


async def _load_analysis_input(
    sample_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> tuple[str | None, bytes, str, str]:
    if sample_id and file is not None:
        raise HTTPException(status_code=400, detail="provide either sample_id or file, not both")
    if not sample_id and file is None:
        raise HTTPException(status_code=400, detail="provide sample_id or file")

    response_sample_id: str | None = None
    if sample_id:
        try:
            sample = get_sample(sample_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="sample not found") from exc
        path = sample_image_path(sample)
        image_bytes = path.read_bytes()
        media_type = _media_type_for_path(path)
        file_name = path.name
        response_sample_id = sample.id
    else:
        assert file is not None
        media_type = file.content_type or ""
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Only PNG, JPEG, and WebP images are supported in this version.",
            )
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="uploaded file is empty")
        file_name = file.filename or f"upload{SUPPORTED_MEDIA_TYPES[media_type]}"
    return response_sample_id, image_bytes, media_type, file_name


async def _run_analysis(
    *,
    response_sample_id: str | None,
    image_bytes: bytes,
    media_type: str,
    file_name: str,
    language: Language,
) -> AnalyzeResponse:
    with agent_span("analyze_drawing"):
        result, regions = await asyncio.gather(
            analyze_drawing(
                image_bytes=image_bytes,
                media_type=media_type,
                file_name=file_name,
                language=language,
            ),
            analyze_layout_regions(image_bytes=image_bytes, media_type=media_type),
        )
        references = match_references(result, regions)
    return AnalyzeResponse(
        sample_id=response_sample_id,
        file_name=file_name,
        model=get_settings().azure_foundry_model,
        result=result,
        references=references,
    )


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(
    sample_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    language: str = Form(default="de"),
) -> AnalyzeResponse:
    analysis_language = _language(language)
    response_sample_id, image_bytes, media_type, file_name = await _load_analysis_input(
        sample_id=sample_id,
        file=file,
    )

    try:
        return await _run_analysis(
            response_sample_id=response_sample_id,
            image_bytes=image_bytes,
            media_type=media_type,
            file_name=file_name,
            language=analysis_language,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/analyze/stream")
async def analyze_stream(
    sample_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    language: str = Form(default="de"),
) -> StreamingResponse:
    analysis_language = _language(language)
    response_sample_id, image_bytes, media_type, file_name = await _load_analysis_input(
        sample_id=sample_id,
        file=file,
    )

    async def events() -> AsyncIterator[str]:
        try:
            yield _sse("started", {"fileName": file_name, "sampleId": response_sample_id})
            with agent_span("analyze_drawing"):
                yield _sse("layout_started", {})
                layout_task = asyncio.create_task(
                    analyze_layout_regions(image_bytes=image_bytes, media_type=media_type)
                )
                yield _sse("model_started", {})
                model_task = asyncio.create_task(
                    analyze_drawing(
                        image_bytes=image_bytes,
                        media_type=media_type,
                        file_name=file_name,
                        language=analysis_language,
                    )
                )

                regions = None
                result = None
                pending: set[asyncio.Task[object]] = {layout_task, model_task}
                while pending:
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        if task is layout_task:
                            regions = layout_task.result()
                            yield _sse(
                                "layout_completed",
                                {
                                    "regionCount": len(regions),
                                    "regions": [
                                        region.model_dump(mode="json") for region in regions
                                    ],
                                },
                            )
                        elif task is model_task:
                            result = model_task.result()
                            yield _sse("model_completed", {})

                if regions is None or result is None:
                    raise RuntimeError("analysis did not complete")

                yield _sse("grounding_started", {})
                references = match_references(result, regions)

            response = AnalyzeResponse(
                sample_id=response_sample_id,
                file_name=file_name,
                model=get_settings().azure_foundry_model,
                result=result,
                references=references,
            )
            yield _sse("completed", response.model_dump(mode="json"))
        except Exception as exc:
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")
