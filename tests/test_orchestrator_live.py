import pytest

from config import IS_LOCAL, api_key
from delegate_tool import DELEGATE_TOOL_NAME
from orchestrator import Orchestrator

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_key():
    api_key()


def _delegations(orchestrator):
    return [
        block
        for message in orchestrator.messages
        if isinstance(message["content"], list)
        for block in message["content"]
        if getattr(block, "name", None) == DELEGATE_TOOL_NAME
    ]


@pytest.mark.skipif(
    IS_LOCAL, reason="local models do not reliably call tools; run against Claude"
)
def test_multi_concern_query_fans_out_to_specialists():
    orchestrator = Orchestrator(user_id="u_004")
    reply = orchestrator.send("my counsellor never showed up and I want a refund")
    print(f"\n{reply}")
    assert reply.strip()
    assert len(_delegations(orchestrator)) >= 1
    assert orchestrator.verdicts


def test_single_concern_query_still_answers():
    orchestrator = Orchestrator(user_id="u_004")
    reply = orchestrator.send("I want a refund for my counselling plan.")
    print(f"\n{reply}")
    assert reply.strip()
