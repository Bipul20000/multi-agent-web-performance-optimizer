"""Gemini client — LangChain-based wrapper for Google Gemini LLM calls."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from loguru import logger as _logger

logger = _logger.bind(module=__name__)

# ── Custom exceptions ──────────────────────────────────────────────────────


class GeminiError(Exception):
    """Raised when Gemini API calls fail after all retries."""

    def __init__(self, message: str, retries: int = 0) -> None:
        self.retries = retries
        super().__init__(message)


# ── Code fence stripping ──────────────────────────────────────────────────

_CODE_FENCE_RE = re.compile(
    r"^```(?:json|javascript|typescript|python|html|css|jsx|tsx|bash|sh)?\s*\n?"
    r"(.*?)"
    r"\n?```\s*$",
    re.DOTALL,
)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group(1).strip()
    # Handle case where there's text before/after fences
    if "```" in text:
        lines = text.split("\n")
        inside = False
        result_lines: list[str] = []
        for line in lines:
            if line.strip().startswith("```") and not inside:
                inside = True
                continue
            if line.strip() == "```" and inside:
                inside = False
                continue
            if inside:
                result_lines.append(line)
        if result_lines:
            return "\n".join(result_lines).strip()
    return text


# ── Model factories ───────────────────────────────────────────────────────


def get_reasoning_model(api_key: str) -> ChatGoogleGenerativeAI:
    """Return a Gemini 2.5 Pro instance optimised for reasoning tasks.

    Uses temperature=0 for deterministic output and a generous token limit
    for complex analysis and fix-plan generation.
    """
    logger.info("Initialising Gemini reasoning model (gemini-2.5-pro)")
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        google_api_key=api_key,
        temperature=0,
        max_output_tokens=8192,
    )


def get_flash_model(api_key: str) -> ChatGoogleGenerativeAI:
    """Return a Gemini 2.5 Flash instance for fast classification / gating.

    Slightly higher temperature (0.1) for minor creative variance in
    summaries while remaining largely deterministic.
    """
    logger.info("Initialising Gemini flash model (gemini-2.5-flash)")
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0.1,
        max_output_tokens=4096,
    )


from pydantic import SecretStr

def get_groq_reasoning_model(api_key: str):
    primary = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=SecretStr(api_key),
        temperature=0,
        max_tokens=8192,
    )
    fallback = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=SecretStr(api_key),
        temperature=0,
        max_tokens=8192,
    )
    return primary.with_fallbacks([fallback])


def get_groq_flash_model(api_key: str) -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile", 
        api_key=SecretStr(api_key),
        temperature=0.1,
        max_tokens=4096
    )


# ── Structured output ─────────────────────────────────────────────────────


def _build_schema_instruction(output_schema: dict[str, Any]) -> str:
    """Build the JSON-schema instruction appended to user prompts."""
    schema_str = json.dumps(output_schema, indent=2)
    return (
        "\n\nRespond ONLY with valid JSON matching this schema:\n"
        f"{schema_str}\n"
        "No markdown, no explanation, just JSON."
    )


def _validate_keys(data: dict[str, Any], schema: dict[str, Any]) -> None:
    """Verify all top-level required keys from the schema are present."""
    required = set()
    if "required" in schema:
        required = set(schema["required"])
    elif "properties" in schema:
        required = set(schema["properties"].keys())

    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Response JSON missing required keys: {missing}")


async def call_with_structured_output(
    model: Any,
    system_prompt: str,
    user_prompt: str,
    output_schema: dict[str, Any],
    *,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Call Gemini and parse the response as structured JSON.

    Appends a schema instruction to *user_prompt*, invokes the model, strips
    any code fences, parses JSON, and validates required keys.

    Retries up to *max_retries* times on ``JSONDecodeError`` before raising
    :class:`GeminiError`.
    """
    full_prompt = user_prompt + _build_schema_instruction(output_schema)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=full_prompt),
    ]

    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Calling LLM for structured output (attempt {}/{})",
                attempt,
                max_retries,
            )

            response = None
            for attempt_429 in range(3):
                try:
                    response = await model.ainvoke(messages)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt_429 < 2:
                        logger.warning("Rate limited (429), backing off for {}s", 60 * (attempt_429 + 1))
                        await asyncio.sleep(60 * (attempt_429 + 1))
                        continue
                    raise
            raw_text: str = response.content if response and isinstance(response.content, str) else str(response.content) if response else ""
            cleaned = _strip_code_fences(raw_text)

            try:
                parsed: dict[str, Any] = json.loads(cleaned, strict=False)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "JSON parse failed on attempt {}/{}: {} — raw preview: {}",
                    attempt,
                    max_retries,
                    exc,
                    cleaned[:200],
                )
                last_error = exc
                continue

            _validate_keys(parsed, output_schema)

            logger.info(
                "Structured output parsed successfully ({} top-level keys)",
                len(parsed),
            )
            return parsed

        except json.JSONDecodeError:
            raise  # already handled above
        except ValueError as exc:
            logger.warning(
                "Schema validation failed on attempt {}/{}: {}",
                attempt,
                max_retries,
                exc,
            )
            last_error = exc
            continue
        except Exception as exc:
            logger.error("LLM invocation error: {}", exc)
            raise GeminiError(
                f"LLM call failed: {exc}",
                retries=attempt,
            ) from exc

    raise GeminiError(
        f"Failed to get valid JSON from LLM after {max_retries} retries. "
        f"Last error: {last_error}",
        retries=max_retries,
    )


# ── Code generation ───────────────────────────────────────────────────────


async def call_for_code(
    model: Any,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Call Gemini and return clean code (code fences stripped).

    Useful for generating fix patches where the response should be raw
    code without markdown formatting.
    """
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    logger.info("Calling LLM for code generation")

    try:
        response = None
        for attempt_429 in range(3):
            try:
                response = await model.ainvoke(messages)
                break
            except Exception as e:
                if "429" in str(e) and attempt_429 < 2:
                    logger.warning("Rate limited (429), backing off for {}s", 60 * (attempt_429 + 1))
                    await asyncio.sleep(60 * (attempt_429 + 1))
                    continue
                raise
        raw_text: str = response.content if response and isinstance(response.content, str) else str(response.content) if response else ""
        code = _strip_code_fences(raw_text)
        logger.info("Code generation complete ({} chars)", len(code))
        return code
    except Exception as exc:
        logger.error("Gemini code generation failed: {}", exc)
        raise GeminiError(f"Code generation failed: {exc}") from exc
