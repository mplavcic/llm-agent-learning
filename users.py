USER_DB = {
    "u_004": {
        "name": "Priya",
        "email": "priya@example.com",
        "tier": "premium",
        "registration_date": "2024-01-15",
    },
    "u_017": {
        "name": "Daniel",
        "email": "daniel@example.com",
        "tier": "free",
        "registration_date": "2025-06-02",
    },
    "u_031": {
        "name": "Amara",
        "email": "amara@example.com",
        "tier": "enterprise",
        "registration_date": "2023-11-20",
    },
}

PURCHASES = {
    "u_004": [
        {
            "product": "Premium Counselling Plan",
            "purchased_on": "2026-09-20",
            "amount": 12000,
        }
    ],
    "u_017": [
        {
            "product": "Starter Counselling Plan",
            "purchased_on": "2026-01-05",
            "amount": 3000,
        }
    ],
    "u_031": [
        {
            "product": "Enterprise Counselling Suite",
            "purchased_on": "2026-07-14",
            "amount": 60000,
        }
    ],
}


def lookup_user(user_id: str) -> dict:
    return USER_DB.get(user_id, {"error": "user_not_found", "user_id": user_id})


def tier_for(user_id: str | None, default: str = "free") -> str:
    if not user_id:
        return default
    return USER_DB.get(user_id, {}).get("tier", default)


def get_purchases(user_id: str) -> dict:
    if user_id not in USER_DB:
        return {"error": "user_not_found", "user_id": user_id}
    return {"user_id": user_id, "purchases": PURCHASES.get(user_id, [])}