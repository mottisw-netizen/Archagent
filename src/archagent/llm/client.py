"""Claude client used for every judgement the agent makes about language.

The division of labour is deliberate and it is the safety property of this
system: **the model interprets, the drawing measures**.  Claude decides what a
municipal comment means, which element it points at and how to explain a
trade-off; every number that reaches a report comes from the drawing driver.
The model is never asked for a dimension, an area or a compliance verdict.

Responses are constrained with ``output_config.format`` (JSON schema), so the
caller always gets a validated object rather than prose to regex.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
DEFAULT_MAX_TOKENS = 8000
#: Server-side refusal fallback: if a policy classifier declines, the same
#: request is re-run on a fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """The model could not be reached, or returned something unusable."""


@dataclass
class LLMResponse:
    data: dict
    model: str = ""
    usage: dict = field(default_factory=dict)
    cached: bool = False
    served_by: str = ""

    def cost_hint(self) -> str:
        parts = [f"{key}={value}" for key, value in sorted(self.usage.items()) if value]
        return ", ".join(parts)


class LLMClient(Protocol):
    """What the agent needs from a language model."""

    def complete_json(self, system: str, user: str, schema: dict,
                      effort: str | None = None) -> LLMResponse:
        ...


class AnthropicClient:
    """Claude, through the official SDK."""

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None,
                 effort: str = DEFAULT_EFFORT, max_tokens: int = DEFAULT_MAX_TOKENS,
                 timeout: float = 180.0, max_retries: int = 3,
                 fallbacks: bool = True):
        try:
            import anthropic
        except ImportError as error:  # pragma: no cover - depends on the environment
            raise LLMError(
                "the anthropic SDK is not installed; run: pip install 'archagent[llm]'"
            ) from error
        self._anthropic = anthropic
        kwargs: dict[str, Any] = {"timeout": timeout, "max_retries": max_retries}
        if api_key:
            kwargs["api_key"] = api_key
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.fallbacks = fallbacks
        self.calls = 0
        self.usage: dict[str, int] = {}

    # ------------------------------------------------------------------
    def complete_json(self, system: str, user: str, schema: dict,
                      effort: str | None = None) -> LLMResponse:
        anthropic = self._anthropic
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # The system prompt is identical for every comment in a run, so it
            # is cached: the run pays for it once.
            "system": [{"type": "text", "text": system,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": effort or self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        try:
            response = self._create(request)
        except anthropic.APIStatusError as error:
            raise LLMError(f"Claude returned {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise LLMError(f"could not reach Claude: {error}") from error

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMError(f"the request was declined ({getattr(details, 'category', 'unknown')})")

        text = next((block.text for block in response.content if block.type == "text"), "")
        if not text:
            raise LLMError("the model returned no text block")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:  # pragma: no cover - schema makes this rare
            raise LLMError(f"the model returned invalid JSON: {error}") from error

        self.calls += 1
        usage = _usage_dict(getattr(response, "usage", None))
        for key, value in usage.items():
            self.usage[key] = self.usage.get(key, 0) + value
        return LLMResponse(data=data, model=getattr(response, "model", self.model),
                           usage=usage, served_by=getattr(response, "model", ""))

    def _create(self, request: dict):
        """Call the API, preferring the server-side refusal fallback."""
        if self.fallbacks:
            try:
                return self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **request)
            except (TypeError, AttributeError):
                self.fallbacks = False  # SDK too old for this beta; carry on without it
            except self._anthropic.BadRequestError as error:
                if "fallback" not in str(error).casefold() and "beta" not in str(error).casefold():
                    raise
                self.fallbacks = False
        return self.client.messages.create(**request)


class CachingClient:
    """Disk cache around another client.

    The same comment text produces the same interpretation, so a re-run of a
    project - or a test - costs nothing and stays deterministic.
    """

    def __init__(self, inner: LLMClient, directory: Path):
        self.inner = inner
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    @property
    def calls(self) -> int:
        return getattr(self.inner, "calls", 0)

    @property
    def usage(self) -> dict:
        return getattr(self.inner, "usage", {})

    def complete_json(self, system: str, user: str, schema: dict,
                      effort: str | None = None) -> LLMResponse:
        model = getattr(self.inner, "model", "unknown")
        key = hashlib.sha256(json.dumps(
            [model, system, user, schema, effort], sort_keys=True, ensure_ascii=False
        ).encode("utf-8")).hexdigest()[:32]
        path = self.directory / f"{key}.json"
        if path.exists():
            self.hits += 1
            payload = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(data=payload["data"], model=payload.get("model", model),
                               usage=payload.get("usage", {}), cached=True)
        self.misses += 1
        response = self.inner.complete_json(system, user, schema, effort)
        path.write_text(json.dumps(
            {"data": response.data, "model": response.model, "usage": response.usage},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return response


class ScriptedClient:
    """A client backed by a callable - used by the tests and for dry runs."""

    def __init__(self, responder: Callable[[str, str, dict], dict]):
        self.responder = responder
        self.calls = 0
        self.prompts: list[tuple[str, str]] = []
        self.usage: dict[str, int] = {}
        self.model = "scripted"

    def complete_json(self, system: str, user: str, schema: dict,
                      effort: str | None = None) -> LLMResponse:
        self.calls += 1
        self.prompts.append((system, user))
        data = self.responder(system, user, schema)
        if data is None:
            raise LLMError("scripted client has no answer for this prompt")
        return LLMResponse(data=data, model="scripted")


def _usage_dict(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    fields = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens")
    return {name: int(getattr(usage, name, 0) or 0) for name in fields
            if getattr(usage, name, 0)}


def from_env(model: str | None = None, effort: str | None = None,
             cache_dir: Path | str | None = None,
             required: bool = False) -> LLMClient | None:
    """Build a client from the environment.

    Returns ``None`` when no credentials are configured, so the agent can fall
    back to its deterministic parser instead of failing - unless *required*.
    """
    model = model or os.environ.get("ARCHAGENT_MODEL", DEFAULT_MODEL)
    effort = effort or os.environ.get("ARCHAGENT_EFFORT", DEFAULT_EFFORT)
    has_credentials = bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or Path(os.path.expanduser("~/.config/anthropic")).exists()
    )
    if not has_credentials and not required:
        return None
    client: LLMClient = AnthropicClient(model=model, effort=effort)
    cache_dir = cache_dir or os.environ.get("ARCHAGENT_LLM_CACHE")
    if cache_dir:
        client = CachingClient(client, Path(cache_dir))
    return client
