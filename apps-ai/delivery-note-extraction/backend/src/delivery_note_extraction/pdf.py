import io
from dataclasses import dataclass

import pypdfium2 as pdfium

from delivery_note_extraction.telemetry import stage_span

RENDER_SCALE = 2.0
MAX_RENDER_DIMENSION = 2200


@dataclass(frozen=True)
class PageImage:
    page: int
    png_bytes: bytes
    width_px: int
    height_px: int


def render_pdf_pages(pdf_bytes: bytes, max_pages: int) -> list[PageImage]:
    """Render PDF pages to PNG images for the multimodal LLM."""
    with stage_span("pdf_render") as span:
        document = pdfium.PdfDocument(pdf_bytes)
        try:
            page_count = len(document)
            images: list[PageImage] = []
            for index in range(min(page_count, max_pages)):
                page = document[index]
                width_pt, height_pt = page.get_size()
                scale = RENDER_SCALE
                longest = max(width_pt, height_pt) * scale
                if longest > MAX_RENDER_DIMENSION:
                    scale = MAX_RENDER_DIMENSION / max(width_pt, height_pt)
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
                buffer = io.BytesIO()
                pil_image.save(buffer, format="PNG")
                images.append(
                    PageImage(
                        page=index + 1,
                        png_bytes=buffer.getvalue(),
                        width_px=pil_image.width,
                        height_px=pil_image.height,
                    )
                )
            span.set_attributes(
                {
                    "pdf.page_count": page_count,
                    "pdf.rendered_pages": len(images),
                    "pdf.input_bytes": len(pdf_bytes),
                    "pdf.rendered_bytes": sum(len(image.png_bytes) for image in images),
                }
            )
            return images
        finally:
            document.close()
