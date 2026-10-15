from knowledge import KB, search_kb


class TestSearchKb:
    def test_refund_query_hits_refund_policy(self):
        results = search_kb("refund policy")["results"]
        assert results
        assert results[0]["id"] == "refund_policy"

    def test_no_match_returns_empty(self):
        assert search_kb("quantum teleportation") == {"results": []}

    def test_case_and_punctuation_insensitive(self):
        assert search_kb("Refund, Policy!")["results"][0]["id"] == "refund_policy"

    def test_results_include_title_and_text(self):
        doc = search_kb("refund")["results"][0]
        assert doc["title"]
        assert "14 days" in doc["text"]

    def test_kb_is_well_formed(self):
        for doc in KB:
            assert doc["id"] and doc["title"] and doc["text"]
