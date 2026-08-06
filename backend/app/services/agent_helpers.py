def classify_error(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()

    if "timeout" in name or "timeout" in msg:
        return "timeout"
    if "rate" in msg and "limit" in msg:
        return "rate_limit"
    if "structured parse failed" in msg or "parse" in msg:
        return "parsing_error"
    if "connection" in name or "connection" in msg:
        return "connection_error"
    if "auth" in msg or "permission" in msg or "api key" in msg:
        return "auth_error"
    return "unknown"


def extract_token_usage(raw_message) -> tuple[int, int]: # Meta data can be inside raw_message["usage_metadata"] or raw_message["response_metadata"] check both
    usage = getattr(raw_message, "usage_metadata", None)
    if usage:
        return usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0
    usage = getattr(raw_message, "response_metadata", {}) or {}
    token_usage = usage.get("usage_metadata") or usage.get("token_usage") or {}
    return (token_usage.get("prompt_token_count", token_usage.get("input_tokens", 0)) or 0, token_usage.get("candidates_token_count", token_usage.get("output_tokens", 0)) or 0)