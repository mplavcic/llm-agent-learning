import pytest

from agent import Agent
from config import IS_LOCAL, api_key

pytestmark = pytest.mark.integration

REFUND_TURN = "[user_id: u_004]\n\nI want a refund for my counselling plan."


@pytest.fixture(autouse=True)
def _require_key():
    api_key()


def test_refund_turn_answers():
    answer = Agent().chat(REFUND_TURN)
    print(f"\n{answer}")
    assert answer.strip()


@pytest.mark.skipif(
    IS_LOCAL, reason="local models do not reliably call tools; run against Claude"
)
def test_grounded_answer_uses_real_user_data():
    answer = Agent().chat(REFUND_TURN)
    print(f"\n{answer}")
    assert "Priya" in answer
    assert "14" in answer or "day" in answer


def test_unknown_user_recovers_gracefully():
    answer = Agent().chat("[user_id: u_999]\n\nI want a refund.")
    print(f"\n{answer}")
    assert answer.strip()
