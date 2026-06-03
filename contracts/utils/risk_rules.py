# contracts/utils/risk_rules.py

RISK_PATTERNS = {
    "liability": {
        "high": [
            "unlimited liability",
            "without limitation",
            "all damages"
        ],
        "medium": [
            "indirect damages",
            "consequential damages"
        ]
    },

    "payment": {
        "high": [
            "payment due immediately",
            "non-refundable"
        ],
        "medium": [
            "payment due within 7 days"
        ]
    },

    "termination": {
        "high": [
            "termination without notice"
        ],
        "medium": [
            "termination with 90 day notice"
        ]
    }
}  