import asyncio
import base64
import json
from functools import lru_cache

from azure.identity import get_bearer_token_provider
from openai import OpenAI
from openai import OpenAIError
from pydantic import ValidationError

from technical_drawing_analysis.auth import create_credential
from technical_drawing_analysis.models import DrawingAnalysis
from technical_drawing_analysis.models import Language
from technical_drawing_analysis.settings import get_settings
from technical_drawing_analysis.telemetry import stage_span


ATTRIBUTE_TEXT_LIMIT = 8000


LANGUAGE_INSTRUCTIONS: dict[Language, str] = {
    "de": (
        "Write user-facing values in German where they are not raw drawing text: summary, "
        "feature, view, category, review flag messages, and interpretation-like labels. "
        "Keep raw drawing callouts unchanged."
    ),
    "en": (
        "Write user-facing values in English where they are not raw drawing text: summary, "
        "feature, view, category, review flag messages, and interpretation-like labels. "
        "Keep raw drawing callouts unchanged."
    ),
}

USER_PROMPTS: dict[Language, tuple[str, str]] = {
    "de": ("Analysiere diese technische Zeichnung.", "Gib nur das JSON-Objekt zurück."),
    "en": ("Analyze this technical drawing.", "Return only the JSON object."),
}

SYSTEM_PROMPT_PREFIX = """
You analyze manufacturing technical drawings from rendered images.
Extract only information visible in the drawing. Do not invent missing title-block values,
dimensions, materials, revision numbers, or tolerances. Use null for unknown values.
"""

SYSTEM_PROMPT_SCHEMA = """
Return strict JSON matching this object shape:
{
  "summary": "one concise sentence",
  "identity": {
    "title": string|null,
    "drawing_number": string|null,
    "revision": string|null,
    "material": string|null,
    "units": string|null,
    "sheet": string|null,
    "scale": string|null
  },
  "dimensions": [
    {
      "label": "raw callout text",
      "value": number|null,
      "unit": "mm"|string|null,
      "type": "linear|diameter|radius|angle|thread|other",
      "quantity": integer|null,
      "tolerance": {"plus": number|null, "minus": number|null, "text": string|null}|null,
      "feature": string|null,
      "view": string|null,
      "confidence": number from 0 to 1,
      "needs_review": boolean
    }
  ],
  "surface_finish": [
    {
      "label": "raw surface finish callout",
      "type": string|null,
      "value": number|null,
      "confidence": number from 0 to 1,
      "needs_review": boolean
    }
  ],
  "gd_and_t": [
    {
      "label": "raw GD&T callout",
      "symbol": string|null,
      "tolerance": string|null,
      "datum": string|null,
      "confidence": number from 0 to 1,
      "needs_review": boolean
    }
  ],
  "notes": [
    {
      "text": string,
      "category": string|null,
      "confidence": number from 0 to 1,
      "needs_review": boolean
    }
  ],
  "review_flags": [
    {"severity": "low|medium|high", "message": string}
  ]
}
Flag rotated, ambiguous, missing, or hard-to-read information for review.
Keep organization or company names out of the output if any appear in the image.
"""


def _system_prompt(language: Language) -> str:
    return f"{SYSTEM_PROMPT_PREFIX}{LANGUAGE_INSTRUCTIONS[language]}{SYSTEM_PROMPT_SCHEMA}"


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


def _data_url(image_bytes: bytes, media_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _json_from_text(value: str) -> dict[str, object]:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


def _analyze_sync(
    *,
    image_bytes: bytes,
    media_type: str,
    file_name: str,
    language: Language,
) -> DrawingAnalysis:
    settings = get_settings()
    user_intro, user_suffix = USER_PROMPTS[language]
    user_text = f"{user_intro} Dateiname / file name: {file_name}. {user_suffix}"
    with stage_span("model_extraction") as span:
        span.set_attributes(
            {
                "llm.file_name": file_name,
                "llm.language": language,
                "llm.input_bytes": len(image_bytes),
                "llm.media_type": media_type,
                "llm.system_prompt": _system_prompt(language)[:ATTRIBUTE_TEXT_LIMIT],
                "llm.user_text": user_text[:ATTRIBUTE_TEXT_LIMIT],
            }
        )
        response = _client().chat.completions.create(
            model=settings.azure_foundry_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _system_prompt(language)},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_text,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": _data_url(image_bytes, media_type),
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Model returned an empty response.")
        span.set_attributes({"llm.output": content[:ATTRIBUTE_TEXT_LIMIT]})
        return DrawingAnalysis.model_validate(_json_from_text(content))


async def analyze_drawing(
    *,
    image_bytes: bytes,
    media_type: str,
    file_name: str,
    language: Language,
) -> DrawingAnalysis:
    try:
        return await asyncio.to_thread(
            _analyze_sync,
            image_bytes=image_bytes,
            media_type=media_type,
            file_name=file_name,
            language=language,
        )
    except (OpenAIError, ValidationError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Drawing analysis failed: {exc}") from exc
