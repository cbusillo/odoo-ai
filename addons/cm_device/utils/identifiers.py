EMPTY_IDENTIFIER_VALUES = {"n/a", "na", "none", "unknown", "unk", "tbd", "null", "-"}


def clean_identifier_value(value: str | None, *, identifier_type: str) -> str | None:
    if not value:
        return None
    cleaned = " ".join(str(value).strip().split())
    if not cleaned:
        return None
    normalized = cleaned.lower()
    if normalized in EMPTY_IDENTIFIER_VALUES:
        return None
    if identifier_type == "imei":
        digits = "".join(character for character in cleaned if character.isdigit())
        return digits if len(digits) >= 8 else None
    if identifier_type in {"serial", "asset_tag"} and len(cleaned) < 2:
        return None
    return cleaned
