"""Credential redaction for durable Thompson experiment records."""
import os


def sanitize(value):
    secrets = [v for k, v in os.environ.items() if len(v) >= 8 and any(t in k.upper() for t in ("API_KEY", "TOKEN", "SECRET"))]
    def walk(item):
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, "[REDACTED]")
            return item
        if isinstance(item, list):
            return [walk(x) for x in item]
        if isinstance(item, dict):
            return {walk(str(k)): "[REDACTED]" if str(k).lower() in ("authorization", "api_key", "api-key", "access_token") else walk(v) for k, v in item.items()}
        return item
    return walk(value)
