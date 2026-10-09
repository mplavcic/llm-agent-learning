import pytest

from classifier import classify_message
from config import api_key

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_key():
    api_key()


class TestClassify:
    cases = [
        ("I want a refund for my purchase", "refund"),
        ("The app keeps crashing on Android", "technical"),
        ("My counsellor missed our session again", "counsellor"),
        ("I was charged twice this month", "billing"),
        ("How do I change my intake year?", "general"),
        ("Should I get a refund? I bought the plan last week", "refund"),
    ]

    @pytest.mark.parametrize(("message", "expected"), cases)
    def test_categories(self, message, expected):
        result = classify_message(message)
        assert result.category == expected
        assert result.reasoning
        assert result.confidence in {"high", "medium", "low"}
        print(f"\n[{result.category.upper()}] ({result.confidence}) {message}")