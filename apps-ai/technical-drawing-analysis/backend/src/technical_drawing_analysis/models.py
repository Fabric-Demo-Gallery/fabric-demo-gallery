from typing import Literal

from pydantic import BaseModel
from pydantic import Field

Language = Literal["de", "en"]


class SampleDrawing(BaseModel):
    id: str
    title: str
    description: str
    image_path: str
    width: int
    height: int
    expected_focus: list[str]


class AnalyzeRequest(BaseModel):
    sample_id: str | None = None


class DrawingIdentity(BaseModel):
    title: str | None = None
    drawing_number: str | None = None
    revision: str | None = None
    material: str | None = None
    units: str | None = None
    sheet: str | None = None
    scale: str | None = None


class Tolerance(BaseModel):
    plus: float | None = None
    minus: float | None = None
    text: str | None = None


class ExtractedDimension(BaseModel):
    label: str
    value: float | None = None
    unit: str | None = None
    type: str | None = None
    quantity: int | None = None
    tolerance: Tolerance | None = None
    feature: str | None = None
    view: str | None = None
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False


class SurfaceFinish(BaseModel):
    label: str
    type: str | None = None
    value: float | None = None
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False


class GdAndTCallout(BaseModel):
    label: str
    symbol: str | None = None
    tolerance: str | None = None
    datum: str | None = None
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False


class DrawingNote(BaseModel):
    text: str
    category: str | None = None
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False


class ReviewFlag(BaseModel):
    severity: Literal["low", "medium", "high"]
    message: str


class NormalizedPoint(BaseModel):
    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)


class NormalizedBoundingBox(BaseModel):
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)
    x2: int = Field(ge=0, le=1000)
    y2: int = Field(ge=0, le=1000)


class SourceRegion(BaseModel):
    id: str
    text: str
    polygon_norm: list[NormalizedPoint]
    bbox_norm: NormalizedBoundingBox


class GroundingReference(BaseModel):
    id: str
    kind: Literal["identity", "dimension", "surface_finish", "gdt", "note"]
    item_index: int
    label: str
    match_score: float = Field(ge=0, le=1)
    region: SourceRegion


class DrawingAnalysis(BaseModel):
    summary: str
    identity: DrawingIdentity
    dimensions: list[ExtractedDimension]
    surface_finish: list[SurfaceFinish] = Field(default_factory=list)
    gd_and_t: list[GdAndTCallout] = Field(default_factory=list)
    notes: list[DrawingNote] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    sample_id: str | None = None
    file_name: str
    model: str
    result: DrawingAnalysis
    references: list[GroundingReference] = Field(default_factory=list)
