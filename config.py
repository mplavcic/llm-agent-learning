import os

from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL") or None
IS_LOCAL = BASE_URL is not None
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You are a helpful customer support agent. You are polite, concise, "
    "and always try to resolve the user's issue."
)

SUPPORT_SYSTEM_PROMPT = (
    "You are a customer support agent for a study abroad platform. You handle "
    "refund requests, technical issues, billing questions, and counsellor "
    "complaints. Always look up the relevant policy and the user's own data "
    "before giving a definitive answer. Be concise and empathetic, and never "
    "make promises you cannot keep."
)


def api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if BASE_URL:
        return key or "ollama"
    if not key or key == "your_key_here":
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Paste your key into .env "
            "(see .env.example)."
        )
    return key