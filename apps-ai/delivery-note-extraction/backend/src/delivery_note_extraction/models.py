from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

KOPF_FIELDS = ("lieferant", "verlag", "lieferschein_nummer", "herkunftstext", "datum")
POSITION_FIELDS = ("titel", "isbn", "auflage", "menge", "paletten")


class FieldAlternative(BaseModel):
    """A plausible alternative reading offered by the LLM for an uncertain field."""

    value: str
    confidence: float = 0
    hint: str | None = None

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


def _dedupe_alternatives(
    alternatives: list[FieldAlternative], primary: str | int | None
) -> list[FieldAlternative]:
    """Drop alternatives that repeat the primary value or each other."""
    seen = {str(primary).strip()} if primary is not None else set()
    unique: list[FieldAlternative] = []
    for alternative in alternatives:
        key = alternative.value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(alternative)
    return unique


class ExtractedField(BaseModel):
    """One extracted value with LLM self-assessment metadata.

    Also used as the LLM structured-output schema: keep it free of JSON-Schema
    keywords that strict structured outputs reject (e.g. minimum/maximum);
    confidence is clamped and alternatives are capped by validators instead.
    """

    value: str | None = None
    confidence: float = 0
    source_text: str | None = None
    handwritten_correction: bool = False
    alternatives: list[FieldAlternative] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

    @field_validator("alternatives")
    @classmethod
    def _cap_alternatives(cls, value: list[FieldAlternative]) -> list[FieldAlternative]:
        return value[:3]

    @model_validator(mode="after")
    def _drop_duplicate_alternatives(self) -> "ExtractedField":
        self.alternatives = _dedupe_alternatives(self.alternatives, self.value)
        return self


class ExtractedIntField(BaseModel):
    value: int | None = None
    confidence: float = 0
    source_text: str | None = None
    handwritten_correction: bool = False
    alternatives: list[FieldAlternative] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))

    @field_validator("alternatives")
    @classmethod
    def _cap_alternatives(cls, value: list[FieldAlternative]) -> list[FieldAlternative]:
        return value[:3]

    @model_validator(mode="after")
    def _drop_duplicate_alternatives(self) -> "ExtractedIntField":
        self.alternatives = _dedupe_alternatives(self.alternatives, self.value)
        return self


class Kopf(BaseModel):
    lieferant: ExtractedField = Field(default_factory=ExtractedField)
    verlag: ExtractedField = Field(default_factory=ExtractedField)
    lieferschein_nummer: ExtractedField = Field(default_factory=ExtractedField)
    herkunftstext: ExtractedField = Field(default_factory=ExtractedField)
    datum: ExtractedField = Field(default_factory=ExtractedField)


class Position(BaseModel):
    titel: ExtractedField = Field(default_factory=ExtractedField)
    isbn: ExtractedField = Field(default_factory=ExtractedField)
    auflage: ExtractedField = Field(default_factory=ExtractedField)
    menge: ExtractedIntField = Field(default_factory=ExtractedIntField)
    paletten: ExtractedIntField = Field(default_factory=ExtractedIntField)
    seite: int | None = None


class ExtractionResult(BaseModel):
    kopf: Kopf
    positionen: list[Position] = Field(default_factory=list)
    hinweise: list[str] = Field(default_factory=list)


class DerivedValues(BaseModel):
    anzahl_positionen: int
    gesamtmenge: int | None = None
    gesamt_paletten: int | None = None


class NormalizedPoint(BaseModel):
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)


class NormalizedBoundingBox(BaseModel):
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)
    x2: int = Field(ge=0, le=1000)
    y2: int = Field(ge=0, le=1000)


class PageWord(BaseModel):
    text: str
    polygon_norm: list[NormalizedPoint]
    bbox_norm: NormalizedBoundingBox


class PageLayout(BaseModel):
    page: int
    angle: float = 0
    width: float
    height: float
    unit: str = "inch"
    words: list[PageWord] = Field(default_factory=list)


class GroundingRegion(BaseModel):
    """Internal candidate region used for fuzzy grounding (line or word window)."""

    page: int
    text: str
    polygon_norm: list[NormalizedPoint]
    bbox_norm: NormalizedBoundingBox


class GroundingReference(BaseModel):
    field_path: str
    page: int
    match_score: float = Field(ge=0, le=1)
    region_text: str
    polygon_norm: list[NormalizedPoint]
    bbox_norm: NormalizedBoundingBox
    ambiguous: bool = False
    """True when the value was found at several equally plausible spots on the document."""


class Timings(BaseModel):
    ocr_ms: int | None = None
    llm_ms: int | None = None
    grounding_ms: int | None = None
    total_ms: int | None = None


class AnalyzeResponse(BaseModel):
    file_name: str
    model: str
    reasoning_effort: str | None = None
    pages: list[PageLayout] = Field(default_factory=list)
    extraction: ExtractionResult
    derived: DerivedValues
    references: list[GroundingReference] = Field(default_factory=list)
    timings: Timings = Field(default_factory=Timings)


FieldKind = Literal["text", "int"]


def derive_values(extraction: ExtractionResult) -> DerivedValues:
    mengen = [p.menge.value for p in extraction.positionen if p.menge.value is not None]
    paletten = [p.paletten.value for p in extraction.positionen if p.paletten.value is not None]
    return DerivedValues(
        anzahl_positionen=len(extraction.positionen),
        gesamtmenge=sum(mengen) if mengen else None,
        gesamt_paletten=sum(paletten) if paletten else None,
    )
