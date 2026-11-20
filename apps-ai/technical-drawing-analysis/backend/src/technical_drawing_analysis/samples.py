from pathlib import Path

from technical_drawing_analysis.models import Language
from technical_drawing_analysis.models import SampleDrawing


SAMPLES_DIR = Path(__file__).resolve().parent / "sample_data"

SAMPLES_BY_LANGUAGE: dict[Language, tuple[SampleDrawing, ...]] = {
    "de": (
        SampleDrawing(
            id="bracket-holder",
            title="Halter",
            description="Generische Fertigungszeichnung mit Bohrungen, Radien, Oberflächenangabe und Zeichnungskopf.",
            image_path="bracket-holder.png",
            width=1500,
            height=2100,
            expected_focus=[
                "Durchmesserangaben",
                "lineare Maße mit Toleranzen",
                "Oberflächenrauheit",
                "Material und Zeichnungsnummer",
            ],
        ),
        SampleDrawing(
            id="adapter-plate",
            title="Adapterplatte",
            description="Generische Plattenzeichnung mit Lochbild, Fasenhinweisen und Bezugselementen.",
            image_path="adapter-plate.png",
            width=1800,
            height=1300,
            expected_focus=[
                "Lochbild",
                "Außenmaße",
                "Senkungsangaben",
                "Bezugshinweise",
            ],
        ),
        SampleDrawing(
            id="shaft-collar",
            title="Wellenring",
            description="Generische Drehteilzeichnung mit Durchmessern, Längenmaßen und Toleranzen.",
            image_path="shaft-collar.png",
            width=1800,
            height=1300,
            expected_focus=[
                "Durchmessermaße",
                "Längenstaffelung",
                "Gewindeangabe",
                "Oberflächenangabe",
            ],
        ),
    ),
    "en": (
        SampleDrawing(
            id="bracket-holder",
            title="Bracket holder",
            description="Generic manufacturing drawing with holes, radii, surface finish callout, and title block.",
            image_path="bracket-holder.png",
            width=1500,
            height=2100,
            expected_focus=[
                "diameter callouts",
                "linear dimensions with tolerances",
                "surface roughness",
                "material and drawing number",
            ],
        ),
        SampleDrawing(
            id="adapter-plate",
            title="Adapter plate",
            description="Generic plate drawing with hole pattern, chamfer notes, and datum references.",
            image_path="adapter-plate.png",
            width=1800,
            height=1300,
            expected_focus=[
                "hole pattern",
                "overall dimensions",
                "counterbore callouts",
                "datum notes",
            ],
        ),
        SampleDrawing(
            id="shaft-collar",
            title="Shaft collar",
            description="Generic turned-part drawing with diameters, stepped lengths, and tolerances.",
            image_path="shaft-collar.png",
            width=1800,
            height=1300,
            expected_focus=[
                "diameter dimensions",
                "stepped lengths",
                "thread callout",
                "surface finish",
            ],
        ),
    ),
}

SAMPLES = SAMPLES_BY_LANGUAGE["de"]


def list_samples(language: Language = "de") -> list[SampleDrawing]:
    return list(SAMPLES_BY_LANGUAGE[language])


def get_sample(sample_id: str) -> SampleDrawing:
    for sample in SAMPLES:
        if sample.id == sample_id:
            return sample
    raise KeyError(sample_id)


def sample_image_path(sample: SampleDrawing) -> Path:
    return SAMPLES_DIR / sample.image_path
