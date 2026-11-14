"""English explanations and HKD amounts for new customer simulations.

This is a script/currency guard, not a semantic language or arithmetic oracle.
Original provider output is audited before this validator is called.
"""
import re
import unicodedata

RESPONSE_LANGUAGE = "en"
CURRENCY = "HKD"
CONTRACT_VERSION = "english-hkd-v1"


def validate_english_output(decision):
    if not isinstance(decision, dict):
        raise ValueError("Expected a decision object")
    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason.strip() or not re.search(r"[A-Za-z]", reason):
        raise ValueError("Decision reason must contain an English explanation")
    # Allow English punctuation, numbers and Latin place names (including
    # accents), but reject CJK and other non-Latin scripts rather than translate
    # them and misrepresent a translation as the original model response.
    for char in reason:
        if char.isalpha() and "LATIN" not in unicodedata.name(char, ""):
            raise ValueError("Decision reason must be in English; non-Latin script found")
    if re.search(r"\b(?:JPY|USD|CNY|RMB|EUR|GBP|KRW|TWD|SGD|yen|yuan|euros?)\b|[¥￥€£₩]|US\$", reason, re.IGNORECASE):
        raise ValueError("All scenario amounts must remain in HKD; foreign currency found")
    code = decision.get("reason_code", "UNSPECIFIED")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code):
        raise ValueError("reason_code must be an uppercase English code")
