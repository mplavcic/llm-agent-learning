import json
import re

import llm
from pydantic import BaseModel

CATEGORIES = {
    "refund": "user wants money back for a purchase",
    "technical": "app crash, bug, or platform issue",
    "counsellor": "complaint or question about a counsellor",
    "billing": "invoice, payment method, or subscription",
    "general": "anything that does not fit above",
}

CLASSIFIER_SYSTEM_PROMPT = """\
You are a customer support classifier for a study abroad platform.
Classify the user message into exactly one of these categories:
- refund: user wants money back for a purchase
- technical: app crash, bug, or platform issue
- counsellor: complaint or question about a counsellor
- billing: invoice, payment method, or subscription
- general: anything that does not fit above
You must respond in this exact JSON format:
{
  "reasoning": "brief explanation of why this category fits",
  "category": "one of: refund, technical, counsellor, billing, general",
  "confidence": "high, medium, or low"
}
Return only valid JSON. No other text."""

CATEGORY_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


class Classification(BaseModel):
    reasoning: str
    category: str
    confidence: str


def _parse(response_text: str) -> Classification:
    text = response_text.strip()
    if text.startswith("```"):
        match = CATEGORY_RE.match(text)
        if match:
            text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {text!r}") from exc
    return Classification(**data)


def classify_message(
    user_message: str,
    *,
    temperature: float = 0,
    max_tokens: int = 300,
) -> Classification:
    response = llm.ask(
        [{"role": "user", "content": user_message}],
        system=CLASSIFIER_SYSTEM_PROMPT,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _parse(llm.text(response))