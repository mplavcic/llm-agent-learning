import pytest
from pydantic import ValidationError

from classifier import _parse


class TestParse:
    def test_plain_json(self):
        result = _parse(
            '{"reasoning": "wants money back", "category": "refund", "confidence": "high"}'
        )
        assert result.category == "refund"

    def test_json_in_code_fence(self):
        text = (
            '```json\n{"reasoning": "app crash", "category": "technical", '
            '"confidence": "high"}\n```'
        )
        assert _parse(text).category == "technical"

    def test_whitespace_tolerated(self):
        text = (
            '\n  {"reasoning": "other", "category": "general", '
            '"confidence": "low"}\t\n'
        )
        assert _parse(text).category == "general"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="did not return valid JSON"):
            _parse("I think this is a refund!")

    def test_bad_schema_raises(self):
        with pytest.raises(ValidationError):
            _parse('{"reasoning": "x"}')