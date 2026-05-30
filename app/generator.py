import json
import re

from fastapi import HTTPException

from app.models import DocumentChunk


def _compile_prompt(
    chunks: list[DocumentChunk],
    goal: str,
    question_count: int,
    difficulty: str,
) -> str:
    context = "\n\n".join(
        f"[{chunk.chunk_id} pages {chunk.page_start}-{chunk.page_end}]\n{chunk.text}"
        for chunk in chunks
    )
    return (
        f"Goal: {goal}\n"
        f"Question count: {question_count}\n"
        f"Difficulty: {difficulty}\n\n"
        f"{context}\n\n"
        "Return JSON with title and questions."
    )


def _parse_model_json(raw: str) -> dict:
    cleaned = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Model returned invalid JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise HTTPException(status_code=502, detail="Model JSON must include questions list.")
    return payload


def _redacted_prompt_preview(
    chunks: list[DocumentChunk],
    question_count: int,
    difficulty: str,
) -> str:
    sources = "\n".join(
        f"- {chunk.chunk_id} pages {chunk.page_start}-{chunk.page_end}"
        for chunk in chunks
    )
    return (
        f"Question count: {question_count}\n"
        f"Difficulty: {difficulty}\n"
        f"Sources:\n{sources}\n"
        "Context text and output schema omitted"
    )
