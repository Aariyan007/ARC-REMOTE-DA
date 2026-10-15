"""
Thin model adapter for the chat agent.

The agent works with neutral messages so the model provider can change and tests can
script a fake one:

  {"role": "user",  "text": str}
  {"role": "model", "text": str, "calls": [ToolCall], "raw": <provider object or None>}
  {"role": "tool",  "name": str, "response": dict}

Only Gemini is implemented. `raw` carries the provider's own content object for a
model turn so provider-side state (e.g. Gemini thought signatures) survives the
function-call round trip.
"""

import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

DEFAULT_MODEL = "gemini-2.5-flash"
REQUEST_TIMEOUT_MS = 60_000


class LLMError(Exception):
    """Raised with a message that is safe to show the user."""


@dataclass
class ToolCall:
    name: str
    args: dict = field(default_factory=dict)
    id: Optional[str] = None


@dataclass
class LLMResponse:
    text: str = ""
    calls: List[ToolCall] = field(default_factory=list)
    raw: Any = None


def api_key() -> str:
    return os.getenv("API_KEY", "").strip()


def chat_model() -> str:
    return os.getenv("ARC_CHAT_MODEL", "").strip() or DEFAULT_MODEL


class GeminiLLM:
    def __init__(self, key: Optional[str] = None, model: Optional[str] = None):
        self.key = key or api_key()
        self.model = model or chat_model()
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as e:
                raise LLMError("The Gemini SDK is not installed (pip install google-genai).") from e
            self._client = genai.Client(
                api_key=self.key,
                http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
            )
        return self._client

    # ── conversion (no network; unit-tested) ─────────────────

    @staticmethod
    def to_contents(messages: list):
        from google.genai import types
        contents = []
        for m in messages:
            role = m["role"]
            if role == "user":
                contents.append(types.Content(role="user", parts=[types.Part(text=m["text"])]))
            elif role == "model":
                if m.get("raw") is not None:
                    contents.append(m["raw"])
                    continue
                parts = []
                if m.get("text"):
                    parts.append(types.Part(text=m["text"]))
                for c in m.get("calls") or []:
                    parts.append(types.Part.from_function_call(name=c.name, args=c.args))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                part = types.Part.from_function_response(name=m["name"], response=m["response"])
                # All responses to one model turn must travel in a single user content.
                if contents and contents[-1].role == "user" and contents[-1].parts \
                        and contents[-1].parts[0].function_response is not None:
                    contents[-1].parts.append(part)
                else:
                    contents.append(types.Content(role="user", parts=[part]))
        return contents

    @staticmethod
    def declarations(tools: list):
        from google.genai import types
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(name=t.name, description=t.description,
                                      parameters_json_schema=t.parameters)
            for t in tools
        ])] if tools else None

    @staticmethod
    def parse_response(resp) -> LLMResponse:
        cands = getattr(resp, "candidates", None) or []
        if not cands or not getattr(cands[0], "content", None):
            reason = getattr(cands[0], "finish_reason", None) if cands else None
            raise LLMError(f"The model returned no answer{f' ({reason})' if reason else ''}.")
        content = cands[0].content
        text_parts, calls = [], []
        for part in content.parts or []:
            fc = getattr(part, "function_call", None)
            if fc is not None and getattr(fc, "name", None):
                calls.append(ToolCall(name=fc.name, args=dict(fc.args or {}), id=getattr(fc, "id", None)))
            elif getattr(part, "text", None) and not getattr(part, "thought", False):
                text_parts.append(part.text)
        return LLMResponse(text="".join(text_parts).strip(), calls=calls, raw=content)

    # ── call ─────────────────────────────────────────────────

    def generate(self, messages: list, system: str, tools: list) -> LLMResponse:
        if not self.key:
            raise LLMError("Chat needs a Gemini API key. Set API_KEY in the server's .env and restart.")
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=self.declarations(tools),
            temperature=0.2,
            # We run the tool loop ourselves so every state-changing call can be confirmed.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            resp = self._get_client().models.generate_content(
                model=self.model, contents=self.to_contents(messages), config=config)
        except LLMError:
            raise
        except Exception as e:
            status = getattr(e, "code", None) or getattr(e, "status_code", None)
            if status in (401, 403):
                raise LLMError("The Gemini API key was rejected. Check API_KEY in the server's .env.") from e
            if status == 429:
                raise LLMError("Gemini is rate-limiting requests. Try again in a minute.") from e
            raise LLMError(f"Could not reach the AI model ({e.__class__.__name__}).") from e
        return self.parse_response(resp)


def get_default_llm() -> Optional[GeminiLLM]:
    """The configured model, or None when no API key is set."""
    return GeminiLLM() if api_key() else None
