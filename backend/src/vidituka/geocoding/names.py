"""Name variants used when matching feed names to the gazetteer.

Both sides go through the same canonical form, so for example these pairs end up with a
key in common:

- "СВ. КИРИЛ И МЕТОДИЈ" and "Кирил и Методиј" (leading "Свети")
- "3-ТА МАКЕДОНСКА БРИГАДА" and "Трета македонска бригада" (ordinals)
- "ГЕНЕРАЛ ВАСКО КАРАНГЕЛЕВСКИ" and "Васко Карангелевски" (titles)
- "ГОЦЕ ДЕЛЧЕВ" and "Ѓорѓи (Гоце) Делчев" (a nickname in brackets)
- "ЈОРДАН ЧОПЕЛА" and "Јордан Чопела-Кулак" (a nickname after a dash)
- "МАРШАЛ ТИТО" and "Marshal Tito" (Latin script in OSM)
"""

from __future__ import annotations

import re

from vidituka.gazetteer.names import name_key

# words that only say what kind of place or person it is
_LEADING_WORDS = re.compile(
    r"^(?:СВЕТИ|СВЕТА|СВ|НАСЕЛБА|НАС|СЕЛО|С|НАРОДЕН ХЕРОЈ|ГЕНЕРАЛ ПОЛКОВНИК|ГЕНЕРАЛ"
    r"|АКАДЕМИК|ПРОФ|ДР)\s+"
)
_ORDINALS = {
    "ПРВА": "1", "ПРВИ": "1", "ВТОРА": "2", "ВТОРИ": "2", "ТРЕТА": "3", "ТРЕТИ": "3",
    "ЧЕТВРТА": "4", "ЧЕТВРТИ": "4", "ПЕТТА": "5", "ПЕТТИ": "5", "ШЕСТА": "6", "ШЕСТИ": "6",
    "СЕДМА": "7", "СЕДМИ": "7", "ОСМА": "8", "ОСМИ": "8", "ДЕВЕТТА": "9", "ДЕВЕТТИ": "9",
    "ДЕСЕТТА": "10", "ДЕСЕТТИ": "10", "ЕДИНАЕСЕТТА": "11", "ДВАНАЕСЕТТА": "12",
}  # fmt: skip
# "3 ТА", "3ТА", "11 ТИ" -> "3", "11"
_NUMBER_SUFFIX = re.compile(r"\b(\d+)\s*(?:ТА|ТИ|ВА|ВИ|РА|РИ|МА|МИ)\b")
_BRACKETED = re.compile(r"\s*\(([^)]*)\)")
# "Чопела-Кулак": a nickname joined to the last word
_NICKNAME = re.compile(r"(?<=\w)-[^\s-]+$")

# Macedonian Latin spellings, longest first
_LATIN = [
    ("DZH", "Џ"), ("DŽ", "Џ"), ("GJ", "Ѓ"), ("KJ", "Ќ"), ("DZ", "Ѕ"), ("LJ", "Љ"), ("NJ", "Њ"),
    ("ZH", "Ж"), ("CH", "Ч"), ("SH", "Ш"), ("Ž", "Ж"), ("Č", "Ч"), ("Š", "Ш"), ("Ć", "Ќ"),
    ("Ǵ", "Ѓ"), ("Ḱ", "Ќ"), ("A", "А"), ("B", "Б"), ("V", "В"), ("G", "Г"), ("D", "Д"),
    ("E", "Е"), ("Z", "З"), ("I", "И"), ("J", "Ј"), ("K", "К"), ("L", "Л"), ("M", "М"),
    ("N", "Н"), ("O", "О"), ("P", "П"), ("R", "Р"), ("S", "С"), ("T", "Т"), ("U", "У"),
    ("F", "Ф"), ("H", "Х"), ("C", "Ц"), ("W", "В"), ("Y", "Ј"), ("Q", "К"), ("X", "КС"),
]  # fmt: skip
_HAS_LATIN = re.compile(r"[A-Za-z]")


def match_keys(*names: str) -> frozenset[str]:
    """Every key a gazetteer name should be found under."""
    keys: set[str] = set()
    for name in names:
        for variant in _variants(name):
            key = name_key(variant)
            if key:
                keys.add(key)
                keys.add(canonical(key))
    keys.discard("")
    return frozenset(keys)


def query_key(name: str) -> str:
    """The key a name from the feed is looked up with."""
    return canonical(name_key(_to_cyrillic(name)))


def canonical(key: str) -> str:
    key = _NUMBER_SUFFIX.sub(r"\1", key)
    key = " ".join(_ORDINALS.get(word, word) for word in key.split())
    while True:
        shorter = _LEADING_WORDS.sub("", key)
        if shorter == key or not shorter:
            return key
        key = shorter


def _variants(name: str) -> set[str]:
    name = _to_cyrillic(name)
    found = {name}
    bracket = _BRACKETED.search(name)
    if bracket:
        found.add(_BRACKETED.sub("", name))
        # "Ѓорѓи (Гоце) Делчев" -> "Гоце Делчев"
        before = name[: bracket.start()].rsplit(" ", 1)
        head = before[0] + " " if len(before) == 2 else ""
        found.add(head + bracket.group(1) + name[bracket.end() :])
    found |= {_NICKNAME.sub("", v) for v in found}
    return found


def _to_cyrillic(name: str) -> str:
    if not _HAS_LATIN.search(name):
        return name
    text = name.upper()
    for latin, cyrillic in _LATIN:
        text = text.replace(latin, cyrillic)
    return text
