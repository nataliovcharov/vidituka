"""Builds tiny.osm, a hand-made map used by the gazetteer tests.

Run from backend/: uv run python tests/fixtures/osm/make_tiny.py

Country MK: lon 20-23, lat 41-42.
  municipality "Општина Исток" lon 21-22, municipality "Општина Запад" lon 22-23
  settlement "Ново Село" inside Исток, lon 21.2-21.8, lat 41.6-41.9
A strip of a neighbouring country west of lon 20.
"""

from pathlib import Path
from xml.sax.saxutils import quoteattr

nodes: list[str] = []
ways: list[str] = []
relations: list[str] = []
_next = {"node": 1, "way": 1, "relation": 1}


def _id(kind: str) -> int:
    _next[kind] += 1
    return _next[kind] - 1


def tags_xml(tags: dict[str, str]) -> str:
    return "".join(f"<tag k={quoteattr(k)} v={quoteattr(v)}/>" for k, v in tags.items())


def node(lon: float, lat: float, tags: dict[str, str] | None = None) -> int:
    i = _id("node")
    nodes.append(f'<node id="{i}" lat="{lat}" lon="{lon}">{tags_xml(tags or {})}</node>')
    return i


def way(refs: list[int], tags: dict[str, str] | None = None) -> int:
    i = _id("way")
    nds = "".join(f'<nd ref="{r}"/>' for r in refs)
    ways.append(f'<way id="{i}">{nds}{tags_xml(tags or {})}</way>')
    return i


def boundary(lon0: float, lat0: float, lon1: float, lat1: float, tags: dict[str, str]) -> int:
    corners = [node(lon0, lat0), node(lon1, lat0), node(lon1, lat1), node(lon0, lat1)]
    ring = way([*corners, corners[0]])
    i = _id("relation")
    all_tags = {"type": "boundary", "boundary": "administrative", **tags}
    relations.append(
        f'<relation id="{i}"><member type="way" ref="{ring}" role="outer"/>'
        f"{tags_xml(all_tags)}</relation>"
    )
    return i


def street(points: list[tuple[float, float]], tags: dict[str, str]) -> int:
    return way([node(lon, lat) for lon, lat in points], tags)


boundary(20, 41, 23, 42, {"admin_level": "2", "name": "Северна Македонија", "ISO3166-1": "MK"})
boundary(18, 41, 20, 42, {"admin_level": "2", "name": "Друга земја", "ISO3166-1": "XX"})
boundary(21, 41, 22, 42, {"admin_level": "7", "name": "Општина Исток"})
boundary(22, 41, 23, 42, {"admin_level": "7", "name": "Општина Запад"})
boundary(21.2, 41.6, 21.8, 41.9, {"admin_level": "8", "name": "Ново Село", "old_name": "Старо Име"})
boundary(18.5, 41.5, 19.5, 41.8, {"admin_level": "8", "name": "Туѓо Село"})

node(21.5, 41.75, {"place": "village", "name": "Ново Село"})
node(22.5, 41.5, {"place": "suburb", "name": "Нова Населба", "alt_name": "Населба А;Населба Б"})
node(19.0, 41.5, {"place": "village", "name": "Надвор"})

# one street split into three ways, two spellings that give the same key
street([(21.3, 41.7), (21.4, 41.7)], {"highway": "residential", "name": "Јајце"})
street([(21.4, 41.7), (21.5, 41.7)], {"highway": "residential", "name": "Јајце"})
street([(21.5, 41.7), (21.6, 41.7)], {"highway": "residential", "name": "Улица Јајце"})
# same name in the other municipality is a different street
street([(22.3, 41.3), (22.4, 41.3)], {"highway": "residential", "name": "Јајце"})
street([(21.3, 41.8), (21.4, 41.8)], {"highway": "tertiary", "name": "Костурски Херои",
                                     "old_name": "29. Ноември"})  # fmt: skip
# not addresses / not in the country
street([(21.3, 41.85), (21.4, 41.85)], {"highway": "footway", "name": "Патека"})
street([(21.3, 41.65), (21.4, 41.65)], {"highway": "residential"})
street([(19.0, 41.6), (19.2, 41.6)], {"highway": "residential", "name": "Странска"})

xml = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="make_tiny.py">\n'
    + "\n".join(nodes + ways + relations)
    + "\n</osm>\n"
)
Path(__file__).with_name("tiny.osm").write_text(xml, "utf-8")
