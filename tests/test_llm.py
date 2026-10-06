import pytest

import llm
from config import SYSTEM_PROMPT, api_key

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_key():
    api_key()


def test_smoke_returns_text_and_usage():
    response = llm.ask([{"role": "user", "content": "Hello, who are you?"}])
    answer = llm.text(response)
    assert answer
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0
    print(
        f"\ninput_tokens={response.usage.input_tokens} "
        f"output_tokens={response.usage.output_tokens}"
    )


def test_system_prompt_shapes_the_answer():
    messages = [{"role": "user", "content": "I want a refund for my purchase."}]
    with_persona = llm.text(llm.ask(messages, system=SYSTEM_PROMPT))
    without_persona = llm.text(llm.ask(messages))
    assert with_persona != without_persona
    print(f"\nwith system:    {with_persona!r}")
    print(f"without system: {without_persona!r}")


def test_temperature_zero_is_deterministic():
    messages = [{"role": "user", "content": "Classify this message: my card was charged twice."}]
    first = llm.text(llm.ask(messages, temperature=0))
    second = llm.text(llm.ask(messages, temperature=0))
    assert first == second


def test_stateless_no_memory_between_calls():
    llm.ask([{"role": "user", "content": "My name is Mateo. Remember it."}])
    response = llm.ask([{"role": "user", "content": "What is my name?"}])
    answer = llm.text(response)
    assert "Mateo" not in answer
    print(f"\nsecond call answer: {answer!r}")
