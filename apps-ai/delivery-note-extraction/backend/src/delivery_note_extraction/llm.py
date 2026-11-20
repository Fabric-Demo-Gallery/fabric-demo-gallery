import asyncio
import base64
from functools import lru_cache
from typing import cast

from azure.identity import get_bearer_token_provider
from openai import OpenAI
from openai import OpenAIError
from openai.lib._pydantic import to_strict_json_schema
from openai.types.chat import ChatCompletionContentPartParam
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from openai.types.shared_params import ReasoningEffort
from pydantic import ValidationError

from delivery_note_extraction.auth import create_credential
from delivery_note_extraction.models import ExtractionResult
from delivery_note_extraction.pdf import PageImage
from delivery_note_extraction.settings import get_settings
from delivery_note_extraction.telemetry import stage_span

ATTRIBUTE_TEXT_LIMIT = 8000

SYSTEM_PROMPT = """
You extract structured data from scanned delivery notes (Lieferscheine) of the
German book industry, captured at goods receipt by a logistics fulfillment
provider. The scans come from different printers, may be rotated or stamped,
and often carry handwritten notes and corrections.

Rules:
- Extract only what is visible on the document. Never invent values. Use null
  for missing or unreadable values.
- Handwritten corrections beat printed values: if a printed value is crossed
  out and corrected by hand (e.g. quantity "340" corrected to "352 Ex"), the
  handwritten value is the extracted value. Set "handwritten_correction": true
  for that field.
- "source_text" is the literal text on the document the value came from (for
  corrections: the handwritten text). Keep it short - the exact snippet, not
  the whole line, no paraphrase.
- "confidence" is your honest self-assessment from 0.0 to 1.0:
  0.9-1.0 = clearly printed and unambiguous; 0.7-0.9 = readable but layout or
  assignment uncertain; below 0.7 = hard to read, ambiguous, occluded, or
  guessed. Handwriting is capped at 0.85.
- "alternatives": for every field, list up to 3 other plausible readings
  visible on the document - other candidates that could be mistaken for this
  field (another date, a nearby number, order number vs. delivery note
  number, another company in the letterhead). Provide them even when you are
  confident in the primary value, each scored with its own (then low)
  confidence and a short German "hint" naming where it comes from (e.g.
  "Datum im Stempel", "Auftragsnummer daneben"). Never invent a value, never
  repeat the primary value. Leave the list empty only when nothing else on
  the document could plausibly be this field.
- A delivery note has one header (Kopf) and 1-n line items (Positionen). Book
  title, ISBN, Auflage, quantity, and pallet count belong to the position.

Field definitions (German domain terms are kept as-is):
- kopf.lieferant: sender/printer delivering the goods (usually the letterhead).
- kopf.verlag: publisher / client of the print job (e.g. "Example Publishing"),
  not the logistics provider receiving the goods.
- kopf.lieferschein_nummer: delivery note number (formats vary a lot).
- kopf.herkunftstext: origin/plant of the print run (e.g. "Example Print North",
  "Example Print South"); often the supplier's plant; null if not recognizable.
- kopf.datum: delivery note date, formatted DD.MM.YYYY.
- positionen[].titel: book/article title of the position.
- positionen[].isbn: ISBN or article number (keep hyphens as printed).
- positionen[].auflage: edition number as text (e.g. "04", "3").
- positionen[].menge: quantity (copies) of the position, integer.
- positionen[].paletten: pallet count of the position
  ("Gleichpaletten"/identical pallets), null if not stated.
- positionen[].seite: 1-based page number the position appears on.
- hinweise: short notes for the clerk in German (unreadable spots, stamps,
  deviations, anything unusual). Empty list if nothing to report.

The UI is German-facing: write "hinweise" in German. All extracted values stay
exactly as printed on the document.
"""

USER_PROMPT = (
    "Extract the delivery note data from the following page scans. "
    "File name: {file_name}. Pages are in order."
)


def _base_url() -> str:
    settings = get_settings()
    if not settings.azure_foundry_model:
        raise RuntimeError("AZURE_FOUNDRY_MODEL must be configured.")
    if settings.azure_openai_endpoint:
        return f"{settings.azure_openai_endpoint.rstrip('/')}/openai/v1/"
    if settings.azure_ai_project_endpoint:
        return f"{settings.azure_ai_project_endpoint.rstrip('/')}/openai/v1/"
    raise RuntimeError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT must be configured.")


@lru_cache
def _client() -> OpenAI:
    settings = get_settings()
    token_provider = get_bearer_token_provider(create_credential(), settings.azure_token_scope)
    return OpenAI(api_key=token_provider, base_url=_base_url())


def _data_url(png_bytes: bytes) -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _response_format() -> ResponseFormat:
    """Strict structured-output schema generated from the pydantic model.

    Same schema `chat.completions.parse` builds internally, but passed to
    `create` so the OpenTelemetry OpenAI instrumentation (which only wraps
    `create`) emits the standard GenAI chat span for Foundry tracing.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": ExtractionResult.__name__,
            "schema": to_strict_json_schema(ExtractionResult),
            "strict": True,
        },
    }


def _extract_sync(
    *,
    page_images: list[PageImage],
    file_name: str,
    model: str,
    reasoning_effort: str | None,
) -> ExtractionResult:
    user_text = USER_PROMPT.format(file_name=file_name)
    with stage_span("model_extraction") as span:
        span.set_attributes(
            {
                "llm.file_name": file_name,
                "llm.model": model,
                "llm.reasoning_effort": reasoning_effort or "",
                "llm.pages": len(page_images),
                "llm.input_bytes": sum(len(image.png_bytes) for image in page_images),
                "llm.system_prompt": SYSTEM_PROMPT[:ATTRIBUTE_TEXT_LIMIT],
                "llm.user_text": user_text[:ATTRIBUTE_TEXT_LIMIT],
            }
        )
        content_parts: list[ChatCompletionContentPartParam] = [
            {"type": "text", "text": user_text}
        ]
        for image in page_images:
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _data_url(image.png_bytes), "detail": "high"},
                }
            )
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content_parts},
        ]
        # Strict structured output: the JSON schema is generated from the
        # pydantic model, so prompt and parsing cannot drift apart.
        if reasoning_effort is not None:
            completion = _client().chat.completions.create(
                model=model,
                messages=messages,
                response_format=_response_format(),
                reasoning_effort=cast(ReasoningEffort, reasoning_effort),
            )
        else:
            completion = _client().chat.completions.create(
                model=model,
                messages=messages,
                response_format=_response_format(),
            )
        message = completion.choices[0].message
        if message.refusal:
            raise ValueError(f"Model refused the request: {message.refusal}")
        if not message.content:
            raise ValueError("Model returned no parsable structured output.")
        span.set_attributes({"llm.output": message.content[:ATTRIBUTE_TEXT_LIMIT]})
        return ExtractionResult.model_validate_json(message.content)


async def extract_delivery_note(
    *,
    page_images: list[PageImage],
    file_name: str,
    model: str,
    reasoning_effort: str | None = None,
) -> ExtractionResult:
    try:
        return await asyncio.to_thread(
            _extract_sync,
            page_images=page_images,
            file_name=file_name,
            model=model,
            reasoning_effort=reasoning_effort,
        )
    except (OpenAIError, ValidationError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Delivery note extraction failed: {exc}") from exc
