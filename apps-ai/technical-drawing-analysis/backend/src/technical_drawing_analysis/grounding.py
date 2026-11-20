import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from typing import Any

from technical_drawing_analysis.auth import create_credential
from technical_drawing_analysis.models import DrawingAnalysis
from technical_drawing_analysis.models import GroundingReference
from technical_drawing_analysis.models import NormalizedBoundingBox
from technical_drawing_analysis.models import NormalizedPoint
from technical_drawing_analysis.models import SourceRegion
from technical_drawing_analysis.settings import get_settings
from technical_drawing_analysis.telemetry import stage_span


COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
LAYOUT_API_VERSION = "2024-11-30"
MIN_MATCH_SCORE = 0.55
EVENT_TEXT_LIMIT = 120
ATTRIBUTE_JSON_LIMIT = 8000


def _document_intelligence_endpoint() -> str:
    settings = get_settings()
    if settings.azure_ai_services_endpoint:
        return settings.azure_ai_services_endpoint.rstrip("/")
    if settings.azure_ai_project_endpoint:
        match = re.match(r"https://([^.]+)\.services\.ai\.azure\.com/", settings.azure_ai_project_endpoint)
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


def _submit_layout(image_bytes: bytes, media_type: str, token: str) -> str:
    url = (
        f"{_document_intelligence_endpoint()}"
        f"/documentintelligence/documentModels/prebuilt-layout:analyze"
        f"?api-version={LAYOUT_API_VERSION}"
    )
    request = urllib.request.Request(
        url,
        data=image_bytes,
        method="POST",
        headers=_headers(token, media_type),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            operation_location = response.headers.get("operation-location")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Document Intelligence request failed: HTTP {exc.code}: {body}") from exc
    if not operation_location:
        raise RuntimeError("Document Intelligence did not return an operation-location header.")
    return operation_location


def _poll_layout(operation_location: str, token: str) -> tuple[dict[str, Any], int]:
    deadline = time.monotonic() + 90
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


def _regions_from_layout(layout: dict[str, Any]) -> list[SourceRegion]:
    result = layout.get("analyzeResult", {})
    regions: list[SourceRegion] = []
    for page in result.get("pages", []):
        width = float(page.get("width") or 1)
        height = float(page.get("height") or 1)
        for line in page.get("lines", []):
            polygon = line.get("polygon") or []
            content = line.get("content") or ""
            if len(polygon) < 8 or not content.strip():
                continue
            points, bbox = _normalize_polygon(polygon, width, height)
            regions.append(
                SourceRegion(
                    id=f"line_{len(regions) + 1:03d}",
                    text=content,
                    polygon_norm=points,
                    bbox_norm=bbox,
                )
            )
    return regions


def _normalized_text(value: str) -> str:
    value = value.lower().replace("⌀", "ø").replace("Ø", "ø").replace("±", "+-")
    return re.sub(r"[^a-z0-9ø+\-./]+", "", value)


def _match_score(left: str, right: str) -> float:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if not normalized_left or not normalized_right:
        return 0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return min(len(normalized_left), len(normalized_right)) / max(
            len(normalized_left),
            len(normalized_right),
        )
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _best_region(label: str, regions: list[SourceRegion]) -> tuple[float, SourceRegion | None]:
    if not regions:
        return 0, None
    score, region = max(
        ((_match_score(label, region.text), region) for region in regions),
        key=lambda item: item[0],
    )
    return score, region


def match_references(
    analysis: DrawingAnalysis,
    regions: list[SourceRegion],
) -> list[GroundingReference]:
    with stage_span("match_references") as span:
        references: list[GroundingReference] = []
        candidates = 0
        decisions: list[dict[str, str | bool | int | float]] = []

        def record_match(kind: str, index: int, label: str) -> None:
            nonlocal candidates
            candidates += 1
            score, region = _best_region(label, regions)
            accepted = region is not None and score >= MIN_MATCH_SCORE
            event: dict[str, str | bool | int | float] = {
                "grounding.kind": kind,
                "grounding.item_index": index,
                "grounding.label": label[:EVENT_TEXT_LIMIT],
                "grounding.score": round(score, 3),
                "grounding.accepted": accepted,
            }
            if region is not None:
                event["grounding.region_id"] = region.id
                event["grounding.region_text"] = region.text[:EVENT_TEXT_LIMIT]
            span.add_event("grounding.match", event)
            decisions.append(
                {
                    "kind": kind,
                    "label": label[:EVENT_TEXT_LIMIT],
                    "score": round(score, 3),
                    "ok": accepted,
                    **({"region": region.text[:EVENT_TEXT_LIMIT]} if region is not None else {}),
                }
            )
            if not accepted or region is None:
                return
            references.append(
                GroundingReference(
                    id=f"{kind}-{index}",
                    kind=kind,
                    item_index=index,
                    label=label,
                    match_score=score,
                    region=region,
                )
            )

        identity = analysis.identity
        # Index order must stay in sync with the frontend identity field order.
        identity_values = [
            identity.title,
            identity.drawing_number,
            identity.revision,
            identity.material,
            identity.units,
            identity.sheet,
            identity.scale,
        ]
        for index, value in enumerate(identity_values):
            if not value:
                continue
            record_match("identity", index, value)
        groups = [
            ("dimension", analysis.dimensions, "label"),
            ("surface_finish", analysis.surface_finish, "label"),
            ("gdt", analysis.gd_and_t, "label"),
            ("note", analysis.notes, "text"),
        ]
        for kind, items, label_attr in groups:
            for index, item in enumerate(items):
                record_match(kind, index, getattr(item, label_attr))
        span.set_attributes(
            {
                "grounding.regions": len(regions),
                "grounding.candidates": candidates,
                "grounding.matched": len(references),
                "grounding.dropped": candidates - len(references),
                "grounding.threshold": MIN_MATCH_SCORE,
                "grounding.decisions": json.dumps(decisions, ensure_ascii=False)[
                    :ATTRIBUTE_JSON_LIMIT
                ],
            }
        )
    return references


def _analyze_layout_sync(image_bytes: bytes, media_type: str) -> list[SourceRegion]:
    with stage_span("layout_analysis") as span:
        token = create_credential().get_token(COGNITIVE_SCOPE).token
        operation_location = _submit_layout(image_bytes, media_type, token)
        payload, polls = _poll_layout(operation_location, token)
        regions = _regions_from_layout(payload)
        for region in regions:
            span.add_event(
                "layout.region",
                {
                    "layout.region_id": region.id,
                    "layout.region_text": region.text[:EVENT_TEXT_LIMIT],
                },
            )
        region_texts = {region.id: region.text[:EVENT_TEXT_LIMIT] for region in regions}
        span.set_attributes(
            {
                "layout.input_bytes": len(image_bytes),
                "layout.media_type": media_type,
                "layout.polls": polls,
                "layout.pages": len(payload.get("analyzeResult", {}).get("pages", [])),
                "layout.regions": len(regions),
                "layout.region_texts": json.dumps(region_texts, ensure_ascii=False)[
                    :ATTRIBUTE_JSON_LIMIT
                ],
            }
        )
    return regions


async def analyze_layout_regions(image_bytes: bytes, media_type: str) -> list[SourceRegion]:
    return await asyncio.to_thread(_analyze_layout_sync, image_bytes, media_type)
