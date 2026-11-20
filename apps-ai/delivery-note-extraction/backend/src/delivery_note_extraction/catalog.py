"""Runtime discovery of multimodal chat model deployments on the Foundry account.

The Azure OpenAI data-plane deployments API is used because it works with the
same Cognitive Services token the backend already holds for Document
Intelligence - no control-plane RBAC needed. Vision capability is not exposed
as metadata, so deployments are filtered by known multimodal chat-completion
model families.
"""

import json
import re
import threading
import time
import urllib.request
from typing import Any

from pydantic import BaseModel

from delivery_note_extraction.auth import create_credential
from delivery_note_extraction.settings import get_settings

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
DEPLOYMENTS_API_VERSION = "2023-03-15-preview"
CACHE_TTL_SECONDS = 300

# Multimodal (image input) chat-completion families available via /openai/v1
# chat completions. Text-only (gpt-oss, Kimi), responses-only (gpt-5.x-pro),
# and non-chat deployments (realtime, audio, image, embeddings) are excluded.
_MULTIMODAL_CHAT = re.compile(r"^(gpt-4o|gpt-4\.1|gpt-5|gpt-chat|o[1345])", re.IGNORECASE)
_EXCLUDED = re.compile(
    r"(realtime|audio|image|embedding|whisper|tts|dall-e|transcribe|computer-use|oss|-pro)",
    re.IGNORECASE,
)
# Families that accept the reasoning_effort parameter (gpt-chat-latest does not).
_REASONING = re.compile(r"^(o[1345]|gpt-5(?!.*chat))", re.IGNORECASE)


class ModelOption(BaseModel):
    name: str
    model: str
    reasoning_efforts: tuple[str, ...]

    @property
    def supports_reasoning_effort(self) -> bool:
        return bool(self.reasoning_efforts)


def _account_endpoint() -> str:
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


def reasoning_efforts_for_model(model_name: str) -> tuple[str, ...]:
    """Return reasoning efforts accepted by the model family."""
    normalized = model_name.lower()
    gpt5_match = re.match(r"^gpt-5(?:\.(\d+))?(?:$|[-.])", normalized)
    if gpt5_match:
        minor = int(gpt5_match.group(1) or "0")
        if minor >= 6:
            return ("none", "low", "medium", "high", "xhigh", "max")
        if minor >= 2:
            return ("none", "low", "medium", "high", "xhigh")
        if minor == 1:
            return ("none", "low", "medium", "high")
        return ("minimal", "low", "medium", "high")
    if _REASONING.match(normalized):
        return ("low", "medium", "high")
    return ()


def supports_reasoning_effort(model_name: str) -> bool:
    return bool(reasoning_efforts_for_model(model_name))


def _is_multimodal_chat(model_name: str) -> bool:
    return bool(_MULTIMODAL_CHAT.match(model_name)) and not _EXCLUDED.search(model_name)


def _fetch_deployments() -> list[dict[str, Any]]:
    token = create_credential().get_token(COGNITIVE_SCOPE).token
    url = f"{_account_endpoint()}/openai/deployments?api-version={DEPLOYMENTS_API_VERSION}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


_cache_lock = threading.Lock()
_cache: tuple[float, list[ModelOption]] | None = None


def list_model_options() -> list[ModelOption]:
    """List selectable deployments, cached for a short TTL.

    Falls back to the stale cache if the refresh fails; raises only when no
    listing has ever succeeded.
    """
    global _cache
    with _cache_lock:
        if _cache is not None and time.monotonic() - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]
        try:
            deployments = _fetch_deployments()
        except Exception as exc:
            if _cache is not None:
                return _cache[1]
            raise RuntimeError(f"Could not list model deployments: {exc}") from exc
        options = [
            ModelOption(
                name=str(item.get("id", "")),
                model=str(item.get("model", "")),
                reasoning_efforts=reasoning_efforts_for_model(str(item.get("model", ""))),
            )
            for item in deployments
            if item.get("status") == "succeeded" and _is_multimodal_chat(str(item.get("model", "")))
        ]
        options.sort(key=lambda option: option.name.lower())
        _cache = (time.monotonic(), options)
        return options


def resolve_reasoning_effort(deployment_name: str, requested: str | None) -> str | None:
    """Return the effective reasoning effort for a deployment, or None.

    Uses the live catalog to map deployment name to model family; falls back
    to matching on the deployment name itself if the catalog is unavailable.
    """
    configured = get_settings().azure_foundry_reasoning_effort or None
    try:
        options = {option.name: option for option in list_model_options()}
    except RuntimeError:
        allowed = reasoning_efforts_for_model(deployment_name)
    else:
        option = options.get(deployment_name)
        allowed = (
            option.reasoning_efforts
            if option is not None
            else reasoning_efforts_for_model(deployment_name)
        )
    if not allowed:
        return None
    if requested is not None:
        if requested not in allowed:
            raise ValueError(
                f"reasoning_effort {requested!r} is not supported by {deployment_name}; "
                f"choose one of {', '.join(allowed)}."
            )
        return requested
    return configured if configured in allowed else allowed[0]
