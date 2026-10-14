import re

_PREFIX = re.compile(r"^(?:УЛИЦА|УЛ|БУЛЕВАР|БУЛ|ОПШТИНА|ГРАД)\b\.?\s*")
_PUNCT = re.compile(r"[.,\-–—()\"„“”'/]")


def name_key(name: str) -> str:
    """Comparable form of a place or street name.

    "Улица Никола Петров" and "НИКОЛА ПЕТРОВ" give the same key, as do "1." and "1".
    """
    text = " ".join(name.upper().split())
    text = _PREFIX.sub("", text)
    return " ".join(_PUNCT.sub(" ", text).split())


def split_names(value: str | None) -> list[str]:
    # OSM separates several names in one tag with ";"
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]
