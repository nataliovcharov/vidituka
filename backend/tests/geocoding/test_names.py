from __future__ import annotations

import pytest

from vidituka.geocoding.names import match_keys, query_key


@pytest.mark.parametrize(
    ("feed", "osm"),
    [
        ("СВ. КИРИЛ И МЕТОДИЈ", "Кирил и Методиј"),
        ("3-ТА МАКЕДОНСКА БРИГАДА", "Трета македонска бригада"),
        ("12 МАКЕДОНСКА БРИГАДА", "12-та Македонска бригада"),
        ("ГЕНЕРАЛ ВАСКО КАРАНГЕЛЕВСКИ", "Генерал-Полковник Васко Карангелевски"),
        ("ГОЦЕ ДЕЛЧЕВ", "Ѓорѓи (Гоце) Делчев"),
        ("ЈОРДАН ЧОПЕЛА", "Јордан Чопела-Кулак"),
        ("МАРШАЛ ТИТО", "Marshal Tito"),
        ("ЏЕПЧИШТЕ", "Džepčište"),
        ("НАС. ПИТАРНИЦА", "Питарница"),
    ],
)
def test_feed_and_osm_spellings_share_a_key(feed: str, osm: str) -> None:
    assert query_key(feed) in match_keys(osm)


@pytest.mark.parametrize(
    ("feed", "osm"),
    [
        ("МАКЕДОНСКА БРИГАДА", "Втора македонска бригада"),
        ("ГОЦЕ ДЕЛЧЕВ", "Ѓорѓи Делчев"),
        ("МАКЕДОНСКО", "Македонско-косовска бригада"),
    ],
)
def test_different_names_stay_different(feed: str, osm: str) -> None:
    assert query_key(feed) not in match_keys(osm)
