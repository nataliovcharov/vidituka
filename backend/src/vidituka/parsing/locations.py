"""Rule-based extraction of streets, settlements and neighborhoods from outage text.

The rules follow docs/labeling-guidelines.md. Scored with `vidituka eval-parser`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vidituka.parsing.models import Kind, Location

# names that contain " И " and must not be split on it
NAMES_WITH_AND = ("КИРИЛ И МЕТОДИЈ", "МАРКС И ЕНГЕЛС", "БРАТСТВО И ЕДИНСТВО")
_AND = "⁠И⁠"

_TYPOS = (
    (r"\bБЕ[СЗ]?\s+НАПОЈУВАЊЕ", "БЕЗ НАПОЈУВАЊЕ"),
    (r"\bУЛИЦИТА\b", "УЛИЦИТЕ"),
    (r"\bНАС,", "НАС."),
    (r"\bС\s+\.", "С."),
)

_MARKERS: tuple[tuple[str, Kind], ...] = (
    (r"УЛИЦИТЕ|УЛИЦАТА|УЛИЦА|УЛ|БУЛЕВАР|БУЛ", "street"),
    (r"НАСЕЛБАТА|НАСЕЛБА|НАС", "neighborhood"),
    (r"ОПШТИНА", "municipality"),
    (r"ГРАД", "settlement"),
    (r"С", "settlement"),
)
# a marker is a whole word followed by a space, or an abbreviation ending in a dot
_MARKER_RE = re.compile(
    r"(?P<del>\bДЕЛ(?:ОТ)?\s+(?:ОД\s+)?)?"
    r"\b(?P<marker>(?:УЛИЦИТЕ|УЛИЦАТА|УЛИЦА|БУЛЕВАР|НАСЕЛБАТА|НАСЕЛБА|ОПШТИНА|ГРАД|УЛ|БУЛ)(?=\s)"
    r"|(?:УЛ|БУЛ|НАС|С)\.)"
)
_PLURAL_MARKERS = {"УЛИЦИТЕ"}

_PLURAL_PARTIAL = re.compile(r"\bДЕЛ\s+ОД\s+(?:КОРИСНИЦИТЕ|ПОТРОШУВАЧИТЕ|УЛИЦИТЕ)\b")
_PARTIAL_BEFORE = re.compile(
    r"\b(?:ДЕЛ(?:ОТ)?|КАЈ|ОКОЛУ|ИЗЛЕЗ|БЛИЗИНА|ВЛЕЗОТ|КРСТОСНИЦА\w*)\b(?:\s+\w+){0,2}\s*$"
)
_REFERENCE_BEFORE = re.compile(r"\b(?:ЗА|КОН|ДО|РАСКРСНИЦА\s+СО|ПАТОТ|ПАТ)\s*$")
_SETTLEMENT_LIST_START = re.compile(r"\b(?:КОРИСНИЦИТЕ|ПОТРОШУВАЧИТЕ)\s+ОД\s+(?P<name>.+)$")

# where a name ends: anything after these words is not part of it
_NAME_END = re.compile(
    r"\s+(?:ПОРАДИ|КАКО|ЌЕ|КЕ|СО\s+(?:ОКОЛНИТЕ|СИТЕ|ИНДУСТРИСКИ)|ОД|ДО|КОН|КАЈ|ПОКРАЈ|ОКОЛУ"
    r"|ВО\s+БЛИЗИНА|ВО\s+ПЕРИОД|БЕЗ|ОБЈЕКТИ\w*|ПОТРОШУВАЧИТЕ|КОРИСНИЦИТЕ)\b.*$"
    r"|\s*-\s*ОБЛАСТ\b.*$"
)
_PARTIAL_AFTER = re.compile(r"\s+(?:ОД|ДО|КОН|КАЈ|ОКОЛУ)(?:\s|$)|\s*-\s*ОБЛАСТ\b")
_ENDS_LIST = re.compile(
    r"\b(?:ПОРАДИ|ЧИСТЕЊЕ|ПРОВЕРКА|ДОЛЕВАЊЕ|ДОЛЊВАЊЕ|СО\s+ОКОЛНИТЕ|СО\s+СИТЕ)\b"
)

_NOT_A_PLACE = re.compile(
    r"\b(?:БЕНЗИНСКА|БЕНЗ|МЛЕКАРА|ФАБРИКА|Ф-КА|ФИРМА|ВИНАРИЈА|ЛОКАЛИТЕТ|ЛАДИЛНИК|АЕРОДРОМ|НАПЛАТНА"
    r"|ФАРМА|ЦЕНТРАЛА|ХПП|ТВ|РЕПЕТИТОР\w*|ПОЛИЦИСКА|СТАНИЦА|КАРАУЛА|ОБЈЕКТИ\w*|РУДНИК|ЛТД|ДООЕЛ"
    r"|ЗДРУЖЕНИЕ|САЛОН|МАРКЕТ|УНИВЕРЗИТЕТ|ШКОЛ\w*|ОУ|ЛОВИШТЕ|ПОТРОШУВАЧИТЕ|КОРИСНИЦИТЕ|ТС"
    r"|ИНДУСТРИСК\w*|ПАРКИНГ\w*|ПАЗАР\w*|СТАДИОН\w*|ГРАДИНКА|ПОШТА)\b"
)
_FUNCTION_WORD_START = re.compile(r"^(?:ОД|ДО|НА|ВО|КАЈ|КОН|ЗА|СО|КОИ|И)\b")

_ORDINAL = re.compile(r"^(\d+)\s*-?\s*(ТИ|ТА|ВА|ВИ|МИ|РИ|ТО|ОТ)\b")
_HOUSE_NO = re.compile(r"\s*\bБР\.?\s*(\d+[А-Ш]?)\b")
_TRAILING_NO = re.compile(r"^(?P<name>.*[А-Ш]{3,}.*?)\s+(?P<no>\d+[А-Ш]?)$")
_IN_PLACE = re.compile(r"\s+ВО\s+(?P<place>[А-Ш][А-Ш\s]+)$")
_PREFIX_ABBR = {"СВ.": "СВЕТИ "}


# a dot followed by a space ends a list item, unless it ends an abbreviation like "УЛ."
_SENTENCE_DOT = r"(?<!\bУЛ)(?<!\bБУЛ)(?<!\bС)(?<!\bСВ)(?<!\bНАС)(?<!\bБР)(?<!\bЕЛ)(?<!\b[ДГМ])\.\s+"


@dataclass
class _Chunk:
    text: str
    joined_by_and: bool  # previous separator was " И "


@dataclass
class _State:
    kind: Kind | None = None
    list_partial: bool = False
    carry_partial: bool = False


def parse_locations(text: str, place: str) -> list[Location]:
    """Extract affected locations.

    `place` is the feed's nasMesto, e.g. "ГАЗИ БАБА-СКОПЈЕ-ГАЗИ БАБА".
    """
    place_parts = [p.strip() for p in re.split(r"-", place.upper()) if p.strip()]
    text = _normalize(text)
    state = _State()
    found: list[Location] = []
    run_start = 0

    for chunk in _chunks(text):
        if not chunk.joined_by_and:
            state.carry_partial = False
        _read_chunk(chunk, state, place_parts, found)
        in_place = _IN_PLACE.search(chunk.text)
        if in_place:
            for loc in found[run_start:]:
                if loc.kind == "street" and loc.in_ is None:
                    loc.in_ = in_place.group("place").strip()
        if state.kind is None:
            run_start = len(found)

    return _dedupe(found)


def _read_chunk(
    chunk: _Chunk, state: _State, place_parts: list[str], found: list[Location]
) -> None:
    text = chunk.text
    matches = list(_MARKER_RE.finditer(text))

    if _PLURAL_PARTIAL.search(text):
        state.list_partial = True

    if not matches:
        _read_unmarked(text, state, place_parts, found)
    else:
        prefix = text[: matches[0].start()]
        if prefix.strip() and not _ENDS_LIST.search(prefix):
            _read_unmarked(prefix, state, place_parts, found)
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            left = text[: m.start()]
            kind = _marker_kind(m.group("marker"))
            raw = text[m.end() : end]
            if _REFERENCE_BEFORE.search(left):
                continue
            partial = (
                bool(m.group("del")) or bool(_PARTIAL_BEFORE.search(left)) or state.list_partial
            )
            partial = partial or (chunk.joined_by_and and state.carry_partial)
            partial = partial or bool(_PARTIAL_AFTER.search(raw))
            if m.group("marker") in _PLURAL_MARKERS and m.group("del"):
                state.list_partial = True
            state.kind = kind
            loc = _make_location(kind, raw, partial, place_parts)
            if loc is None:
                # "УЛ.БР 42" right after a name: the number belongs to that name
                number = _HOUSE_NO.search(raw)
                if number and found:
                    found[-1].numbers.append(number.group(1))
                continue
            if m.group("del"):
                state.carry_partial = True
            found.append(loc)

    # words like ПОРАДИ end the list only when they come after the last location
    tail = text[matches[-1].end() :] if matches else text
    if _ENDS_LIST.search(tail):
        state.kind = None
        state.list_partial = False


def _read_unmarked(text: str, state: _State, place_parts: list[str], found: list[Location]) -> None:
    text = text.strip(" .")
    starts_list = _SETTLEMENT_LIST_START.search(text)
    if starts_list:
        state.kind = "settlement"
        text = starts_list.group("name")
    if state.kind is None or not text:
        return
    partial = state.list_partial or state.carry_partial
    lead = re.match(r"^ДЕЛ(?:ОТ)?\s+(?:ОД\s+)?", text)
    if lead:
        partial = True
        state.carry_partial = True
        text = text[lead.end() :]
    partial = partial or bool(_PARTIAL_AFTER.search(text))
    if _FUNCTION_WORD_START.match(text) or _NOT_A_PLACE.search(_NAME_END.sub("", text)):
        state.kind = None
        state.list_partial = False
        return
    loc = _make_location(state.kind, text, partial, place_parts)
    if loc is None:
        return
    if state.kind == "street" and loc.name in place_parts:
        return
    if not _looks_like_name(loc.name):
        return
    found.append(loc)


def _make_location(kind: Kind, raw: str, partial: bool, place_parts: list[str]) -> Location | None:
    text = raw.strip(" .,:")
    numbers = [m.group(1) for m in _HOUSE_NO.finditer(text)]
    text = _HOUSE_NO.sub("", text)
    text = _IN_PLACE.sub("", text)
    text = _NAME_END.sub("", text).strip(" .,:-")
    text = re.sub(r"^(?:ОД|НА)\s+", "", text)
    for abbr, full in _PREFIX_ABBR.items():
        if text.startswith(abbr):
            text = full + text[len(abbr) :].lstrip()
    in_: str | None = None
    if kind == "street":
        for part in place_parts[1:]:
            if text.endswith(" " + part):
                in_ = part
                text = text[: -len(part) - 1].strip()
        ordinal = _ORDINAL.match(text)
        if ordinal:
            rest = text[ordinal.end() :].strip()
            text = ordinal.group(1) if not rest else f"{ordinal.group(1)}-{ordinal.group(2)} {rest}"
        elif not text[:1].isdigit():
            trailing = _TRAILING_NO.match(text)
            if trailing:
                numbers.append(trailing.group("no"))
                text = trailing.group("name").strip()
    else:
        text = _expand_upper_lower(text, place_parts)
    text = " ".join(text.split())
    if not text:
        return None
    return Location(kind=kind, name=text, partial=partial, numbers=numbers, in_=in_)


def _expand_upper_lower(name: str, place_parts: list[str]) -> str:
    """С.Д.ЛЕШНИЦА -> ДОЛНА ЛЕШНИЦА, С.Г.СРПЦИ -> ГОРНО СРПЦИ."""
    m = re.match(r"^([ДГ])\.\s*(.+)$", name)
    if not m:
        return name
    rest = m.group(2).strip()
    for part in place_parts:
        if part.endswith(" " + rest) and part.startswith(m.group(1)):
            return part
    stem = "ДОЛН" if m.group(1) == "Д" else "ГОРН"
    return f"{stem}{'А' if rest.endswith('А') else 'О'} {rest}"


def _looks_like_name(name: str) -> bool:
    words = re.split(r"[\s-]+", name)
    if len(words) > 5:
        return False
    if name.isdigit():
        return True
    return all(len(w) >= 3 or w.isdigit() for w in words if w)


def _marker_kind(marker: str) -> Kind:
    marker = marker.rstrip(".")
    for pattern, kind in _MARKERS:
        if re.fullmatch(pattern, marker):
            return kind
    raise ValueError(marker)


def _normalize(text: str) -> str:
    text = " ".join(text.upper().split())
    for pattern, repl in _TYPOS:
        text = re.sub(pattern, repl, text)
    # a note in brackets saying only part is affected becomes a qualifier
    text = re.sub(r"\(([^)]*\bДЕЛ\w*[^)]*)\)", " КАЈ ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\(\s*\d[\d\s]*", " ", text)  # unclosed "(3803510,"
    for name in NAMES_WITH_AND:
        text = text.replace(name, name.replace(" И ", f" {_AND} "))
    return " ".join(text.split())


def _chunks(text: str) -> list[_Chunk]:
    parts = re.split(r"(\s*[,;]\s*|\s+И\s+|" + _SENTENCE_DOT + ")", text)
    chunks = []
    joined = False
    for i, part in enumerate(parts):
        if i % 2 == 1:
            joined = part.strip() == "И"
            continue
        part = part.replace(f" {_AND} ", " И ").strip()
        if part:
            chunks.append(_Chunk(part, joined))
    return chunks


def _dedupe(found: list[Location]) -> list[Location]:
    out: dict[tuple[str, str], Location] = {}
    for loc in found:
        key = (loc.kind, loc.name)
        if key in out:
            existing = out[key]
            existing.partial = existing.partial and loc.partial
            existing.numbers += [n for n in loc.numbers if n not in existing.numbers]
            existing.in_ = existing.in_ or loc.in_
        else:
            out[key] = loc
    return list(out.values())
