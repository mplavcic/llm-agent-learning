KB = [
    {
        "id": "refund_policy",
        "title": "Refund Policy",
        "text": (
            "Customers may request a full refund within 14 days of the purchase "
            "date. Refunds are issued to the original payment method and take "
            "5-7 business days to process. Plans purchased during a promotional "
            "campaign are non-refundable unless the campaign states otherwise. "
            "Counselling sessions already delivered are non-refundable; only the "
            "unused portion of a plan is eligible. To start a refund, confirm the "
            "purchase date and the original payment method."
        ),
    },
]


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().replace(",", " ").split() if t}


def search_kb(query: str) -> dict:
    query_tokens = _tokens(query)
    scored = []
    for doc in KB:
        haystack = _tokens(f"{doc['title']} {doc['text']}")
        score = len(query_tokens & haystack)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return {"results": [doc for _, doc in scored]}
