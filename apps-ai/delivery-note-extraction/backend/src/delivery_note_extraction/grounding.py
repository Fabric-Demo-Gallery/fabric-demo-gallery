import json
import re
from difflib import SequenceMatcher

from delivery_note_extraction.models import ExtractedField
from delivery_note_extraction.models import ExtractedIntField
from delivery_note_extraction.models import ExtractionResult
from delivery_note_extraction.models import GroundingReference
from delivery_note_extraction.models import GroundingRegion
from delivery_note_extraction.models import KOPF_FIELDS
from delivery_note_extraction.models import NormalizedBoundingBox
from delivery_note_extraction.models import NormalizedPoint
from delivery_note_extraction.models import PageLayout
from delivery_note_extraction.models import POSITION_FIELDS
from delivery_note_extraction.telemetry import stage_span

MIN_MATCH_SCORE = 0.6
MAX_WINDOW_WORDS = 6
EVENT_TEXT_LIMIT = 120
ATTRIBUTE_JSON_LIMIT = 8000
TIE_EPSILON = 0.001
MAX_TIED_MATCHES = 4
SAME_SPOT_OVERLAP = 0.5

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _normalized_text(value: str) -> str:
    value = value.lower().translate(_UMLAUTS)
    return re.sub(r"[^a-z0-9+/]+", "", value)


def _match_score(left_norm: str, right_norm: str) -> float:
    if not left_norm or not right_norm:
        return 0
    if left_norm in right_norm or right_norm in left_norm:
        return min(len(left_norm), len(right_norm)) / max(len(left_norm), len(right_norm))
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _window_regions(pages: list[PageLayout]) -> list[GroundingRegion]:
    """Sliding word windows so short values (e.g. a corrected quantity) ground tightly."""
    regions: list[GroundingRegion] = []
    for page in pages:
        words = page.words
        for start in range(len(words)):
            xs: list[int] = []
            ys: list[int] = []
            texts: list[str] = []
            points: list[NormalizedPoint] = []
            for size in range(1, MAX_WINDOW_WORDS + 1):
                index = start + size - 1
                if index >= len(words):
                    break
                word = words[index]
                texts.append(word.text)
                points = points + list(word.polygon_norm)
                xs.extend([word.bbox_norm.x1, word.bbox_norm.x2])
                ys.extend([word.bbox_norm.y1, word.bbox_norm.y2])
                regions.append(
                    GroundingRegion(
                        page=page.page,
                        text=" ".join(texts),
                        polygon_norm=list(points),
                        bbox_norm=NormalizedBoundingBox(
                            x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys)
                        ),
                    )
                )
    return regions


def _box_area(box: NormalizedBoundingBox) -> int:
    return max(box.x2 - box.x1, 0) * max(box.y2 - box.y1, 0)


def _same_spot(a: GroundingRegion, b: GroundingRegion) -> bool:
    """True when two candidate regions cover the same occurrence on the page."""
    if a.page != b.page:
        return False
    overlap_x = min(a.bbox_norm.x2, b.bbox_norm.x2) - max(a.bbox_norm.x1, b.bbox_norm.x1)
    overlap_y = min(a.bbox_norm.y2, b.bbox_norm.y2) - max(a.bbox_norm.y1, b.bbox_norm.y1)
    if overlap_x <= 0 or overlap_y <= 0:
        return False
    smaller = min(_box_area(a.bbox_norm), _box_area(b.bbox_norm))
    return smaller > 0 and overlap_x * overlap_y / smaller >= SAME_SPOT_OVERLAP


class _RegionIndex:
    def __init__(self, pages: list[PageLayout], line_regions: list[GroundingRegion]) -> None:
        self._regions = line_regions + _window_regions(pages)
        self._normalized = [_normalized_text(region.text) for region in self._regions]

    def matches(self, target: str) -> tuple[float, list[GroundingRegion]]:
        """Best score plus every distinct occurrence tied at that score."""
        target_norm = _normalized_text(target)
        if not target_norm:
            return 0, []
        best_score = 0.0
        tied: list[GroundingRegion] = []
        for region, region_norm in zip(self._regions, self._normalized, strict=True):
            if not region_norm:
                continue
            longer = max(len(target_norm), len(region_norm))
            shorter = min(len(target_norm), len(region_norm))
            if 2 * shorter / (shorter + longer) < best_score - TIE_EPSILON:
                continue  # upper bound of any match score for these lengths
            score = _match_score(target_norm, region_norm)
            if score > best_score + TIE_EPSILON:
                best_score = score
                tied = [region]
            elif score >= best_score - TIE_EPSILON:
                tied.append(region)
        if not tied:
            return best_score, []
        # Tightest boxes first so each occurrence is represented by its snuggest window,
        # then drop candidates that cover a spot we already kept.
        distinct: list[GroundingRegion] = []
        for region in sorted(tied, key=lambda entry: _box_area(entry.bbox_norm)):
            if not any(_same_spot(region, kept) for kept in distinct):
                distinct.append(region)
        distinct.sort(key=lambda entry: (entry.page, entry.bbox_norm.y1, entry.bbox_norm.x1))
        return best_score, distinct[:MAX_TIED_MATCHES]


def _field_entries(
    extraction: ExtractionResult,
) -> list[tuple[str, ExtractedField | ExtractedIntField]]:
    entries: list[tuple[str, ExtractedField | ExtractedIntField]] = []
    for name in KOPF_FIELDS:
        entries.append((f"kopf.{name}", getattr(extraction.kopf, name)))
    for index, position in enumerate(extraction.positionen):
        for name in POSITION_FIELDS:
            entries.append((f"positionen.{index}.{name}", getattr(position, name)))
    return entries


def _target_entries(extraction: ExtractionResult) -> list[tuple[str, str]]:
    """Grounding targets: each field plus its LLM alternatives (path suffix .altN)."""
    targets: list[tuple[str, str]] = []
    for field_path, field in _field_entries(extraction):
        primary = field.source_text or (str(field.value) if field.value is not None else None)
        if primary:
            targets.append((field_path, primary))
        for alt_index, alternative in enumerate(field.alternatives):
            if alternative.value:
                targets.append((f"{field_path}.alt{alt_index}", alternative.value))
    return targets


def match_references(
    extraction: ExtractionResult,
    pages: list[PageLayout],
    line_regions: list[GroundingRegion],
) -> list[GroundingReference]:
    """Attach page bounding boxes to extracted fields via fuzzy source_text matching."""
    with stage_span("grounding") as span:
        index = _RegionIndex(pages, line_regions)
        references: list[GroundingReference] = []
        decisions: list[dict[str, str | bool | int | float]] = []
        candidates = 0
        ambiguous_targets = 0
        for field_path, target in _target_entries(extraction):
            candidates += 1
            score, regions = index.matches(target)
            accepted = bool(regions) and score >= MIN_MATCH_SCORE
            ambiguous = accepted and len(regions) > 1
            if ambiguous:
                ambiguous_targets += 1
            decisions.append(
                {
                    "field": field_path,
                    "target": target[:EVENT_TEXT_LIMIT],
                    "score": round(score, 3),
                    "ok": accepted,
                    **({"tied": len(regions)} if ambiguous else {}),
                    **(
                        {"region": regions[0].text[:EVENT_TEXT_LIMIT], "page": regions[0].page}
                        if regions
                        else {}
                    ),
                }
            )
            if not accepted:
                continue
            for region in regions:
                references.append(
                    GroundingReference(
                        field_path=field_path,
                        page=region.page,
                        match_score=score,
                        region_text=region.text,
                        polygon_norm=region.polygon_norm,
                        bbox_norm=region.bbox_norm,
                        ambiguous=ambiguous,
                    )
                )
        span.set_attributes(
            {
                "grounding.candidates": candidates,
                "grounding.matched": len(references),
                "grounding.ambiguous": ambiguous_targets,
                "grounding.dropped": candidates - len(references),
                "grounding.threshold": MIN_MATCH_SCORE,
                "grounding.decisions": json.dumps(decisions, ensure_ascii=False)[
                    :ATTRIBUTE_JSON_LIMIT
                ],
            }
        )
    return references
