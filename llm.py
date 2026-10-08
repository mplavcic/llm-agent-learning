import anthropic
from anthropic.types import Message

from config import BASE_URL, MAX_TOKENS, MODEL, api_key

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        kwargs: dict = {"api_key": api_key()}
        if BASE_URL:
            kwargs["base_url"] = BASE_URL
        _client = anthropic.Anthropic(**kwargs)
    return _client


def ask(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int = MAX_TOKENS,
    model: str = MODEL,
) -> Message:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    # The current SDK removed `temperature` as a first-class parameter. It is
    # still accepted by the API, so we pass it through as an extra body field.
    if temperature is not None:
        kwargs["extra_body"] = {"temperature": temperature}
    if system is not None:
        kwargs["system"] = system
    return client().messages.create(**kwargs)


def text(response: Message) -> str:
    return "".join(block.text for block in response.content if block.type == "text")
