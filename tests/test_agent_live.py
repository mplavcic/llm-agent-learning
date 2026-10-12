import pytest

from agent import Agent
from config import api_key

pytestmark = pytest.mark.integration

SYSTEM = (
    "You are a helpful customer support agent. Always look up the user's "
    "profile and their purchases before answering questions about their "
    "account. Use the tools available to you."
)


@pytest.fixture(autouse=True)
def _require_key():
    api_key()


def test_grounded_answer_uses_real_user_data():
    agent = Agent(SYSTEM)
    answer = agent.chat("[user_id: u_004]\n\nI want a refund for my counselling plan.")
    print(f"\n{answer}")
    assert "Priya" in answer


def test_unknown_user_recovers_gracefully():
    agent = Agent(SYSTEM)
    answer = agent.chat("[user_id: u_999]\n\nI want a refund.")
    print(f"\n{answer}")
    assert answer.strip()