import os

from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You are a helpful customer support agent. You are polite, concise, "
    "and always try to resolve the user's issue."
)


def api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or key == "your_key_here":
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Paste your key into .env "
            "(see .env.example)."
        )
    return key
