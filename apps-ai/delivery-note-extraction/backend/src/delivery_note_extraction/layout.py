import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from delivery_note_extraction.auth import create_credential
from delivery_note_extraction.models import GroundingRegion
from delivery_note_extraction.models import NormalizedBoundingBox
from delivery_note_extraction.models import NormalizedPoint
from delivery_note_extraction.models import PageLayout
from delivery_note_extraction.models import PageWord
from delivery_note_extraction.settings import get_settings
from delivery_note_extraction.telemetry import stage_span

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
LAYOUT_API_VERSION = "2024-11-30"
POLL_DEADLINE_SECONDS = 180
ATTRIBUTE_JSON_LIMIT = 8000


def _document_intelligence_endpoint() -> str:
    settings = get_settings()
    if settings.azure_ai_services_endpoint:
        return settings.azure_ai_services_endpoint.rstrip("/")
    if settings.azure_ai_project_endpoint:
        match = re.match(
            r"https://([^.]+)\.services\.ai\.azure\.com/", settings.azure_ai_project_endpoint
        )
        if match:
            return f"https://{match.group(1)}.cognitiveservices.azure.com"
    if settings.azure_openai_endpoint:
        return settings.azure_openai_endpoint.rstrip("/")
    raise RuntimeError("AZURE_AI_SERVICES_ENDPOINT or AZURE_AI_PROJECT_ENDPOINT must be configured.")


def _headers(token: str, content_type: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _request_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_headers(token))
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _submit_layout(pdf_bytes: bytes, token: str) -> str:
    url = (
        f"{_document_intelligence_endpoint()}"
        f"/documentintelligence/documentModels/prebuilt-layout:analyze"
        f"?api-version={LAYOUT_API_VERSION}"
    )
    request = urllib.request.Request(
        url,
        data=pdf_bytes,
        method="POST",
        headers=_headers(token, "application/pdf"),
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            operation_location = response.headers.get("operation-location")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Document Intelligence request failed: HTTP {exc.code}: {body}") from exc
    if not operation_location:
        raise RuntimeError("Document Intelligence did not return an operation-location header.")
    return operation_location


def _poll_layout(operation_location: str, token: str) -> tuple[dict[str, Any], int]:
    deadline = time.monotonic() + POLL_DEADLINE_SECONDS
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        payload = _request_json(operation_location, token)
        status = payload.get("status")
        if status == "succeeded":
            return payload, polls
        if status == "failed":
            raise RuntimeError(f"Document Intelligence layout failed: {payload}")
        time.sleep(1)
    raise RuntimeError("Document Intelligence layout timed out.")


def _normalize_polygon(
    polygon: list[float],
    width: float,
    height: float,
) -> tuple[list[NormalizedPoint], NormalizedBoundingBox]:
    points: list[NormalizedPoint] = []
    xs: list[int] = []
    ys: list[int] = []
    for x, y in zip(polygon[0::2], polygon[1::2], strict=False):
        nx = max(0, min(1000, round(x * 1000 / width)))
        ny = max(0, min(1000, round(y * 1000 / height)))
        points.append(NormalizedPoint(x=nx, y=ny))
        xs.append(nx)
        ys.append(ny)
    return points, NormalizedBoundingBox(x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))


def _layout_from_payload(payload: dict[str, Any]) -> tuple[list[PageLayout], list[GroundingRegion]]:
    result = payload.get("analyzeResult", {})
    pages: list[PageLayout] = []
    regions: list[GroundingRegion] = []
    for page_payload in result.get("pages", []):
        page_number = int(page_payload.get("pageNumber") or len(pages) + 1)
        width = float(page_payload.get("width") or 1)
        height = float(page_payload.get("height") or 1)
        angle = float(page_payload.get("angle") or 0)
        unit = str(page_payload.get("unit") or "inch")
        words: list[PageWord] = []
        for word_payload in page_payload.get("words", []):
            polygon = word_payload.get("polygon") or []
            content = word_payload.get("content") or ""
            if len(polygon) < 8 or not content.strip():
                continue
            points, bbox = _normalize_polygon(polygon, width, height)
            words.append(PageWord(text=content, polygon_norm=points, bbox_norm=bbox))
        for line_payload in page_payload.get("lines", []):
            polygon = line_payload.get("polygon") or []
            content = line_payload.get("content") or ""
            if len(polygon) < 8 or not content.strip():
                continue
            points, bbox = _normalize_polygon(polygon, width, height)
            regions.append(
                GroundingRegion(
                    page=page_number,
                    text=content,
                    polygon_norm=points,
                    bbox_norm=bbox,
                )
            )
        pages.append(
            PageLayout(
                page=page_number,
                angle=angle,
                width=width,
                height=height,
                unit=unit,
                words=words,
            )
        )
    return pages, regions


def _analyze_layout_sync(pdf_bytes: bytes) -> tuple[list[PageLayout], list[GroundingRegion]]:
    with stage_span("layout_analysis") as span:
        token = create_credential().get_token(COGNITIVE_SCOPE).token
        operation_location = _submit_layout(pdf_bytes, token)
        payload, polls = _poll_layout(operation_location, token)
        pages, regions = _layout_from_payload(payload)
        span.set_attributes(
            {
                "layout.input_bytes": len(pdf_bytes),
                "layout.polls": polls,
                "layout.pages": len(pages),
                "layout.words": sum(len(page.words) for page in pages),
                "layout.line_regions": len(regions),
                "layout.page_angles": json.dumps(
                    {page.page: round(page.angle, 2) for page in pages}
                ),
                "layout.line_texts": json.dumps(
                    [region.text for region in regions], ensure_ascii=False
                )[:ATTRIBUTE_JSON_LIMIT],
            }
        )
    return pages, regions


async def analyze_layout(pdf_bytes: bytes) -> tuple[list[PageLayout], list[GroundingRegion]]:
    """Run Document Intelligence prebuilt-layout on the full PDF."""
    return await asyncio.to_thread(_analyze_layout_sync, pdf_bytes)
