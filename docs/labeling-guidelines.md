# Labeling guidelines: outage locations

These rules define the "correct answer" for the address parser. The labeled set in
`backend/tests/fixtures/labels/` follows them, and the parser is scored against it.

## What gets labeled

For each outage text, list every **location that loses supply**, as one of:

| kind | when | examples |
|---|---|---|
| `street` | marked with `УЛ.`, `УЛИЦА`, `УЛИЦИТЕ`, `БУЛ.`, or listed among streets | `УЛ.АВРОРА`, `БУЛ.ГОЦЕ ДЕЛЧЕВ` |
| `settlement` | a village or town, usually `С.` | `С.СЕДЛАРЕВО`, `ДЕМИР ХИСАР` |
| `neighborhood` | part of a town, usually `НАС.`, `НАСЕЛБА` | `НАСЕЛБА ПИТАРНИЦА` |
| `municipality` | a whole municipal area, `ОПШТИНА` | `ОПШТИНА РОСОМАН` |

Not labeled:
- companies, shops, schools, substations (`ТС ...`), repeaters, roads named only as directions
- places mentioned only as a reference point, e.g. `ДО РАСКРСНИЦА СО УЛ.X`, `ПАТ ЗА С.Y`
- the reason for the work, dates and times written inside the text

A text that names only companies gets an empty list.

## Names

- Uppercase, as written. Do not fix spelling of names (`ПЕТРЕ ЃЕОРГИЕВ` stays as is);
  matching spelling variants is the geocoder's job.
- Expand abbreviations when the full form is clear from the text or `nasMesto`:
  `СВ.` → `СВЕТИ`, `МАК.` → `МАКЕДОНСКО`, `С.Д.ЛЕШНИЦА` → `ДОЛНА ЛЕШНИЦА`,
  `С.Г.РЕЧИЦА` with place `ТЕТОВО-ГОЛЕМА РЕЧИЦА` → `ГОЛЕМА РЕЧИЦА`.
  If it is not clear, keep the abbreviation and set `uncertain`.
- Numbered streets are just the number: `УЛ.21-ВА` → `21`, `УЛ. 10` → `10`.
- Streets whose name starts with an ordinal keep it with a hyphen:
  `12 - ТА МАКЕДОНСКА БРИГАДА` → `12-ТА МАКЕДОНСКА БРИГАДА`, `29 ТИ НОЕМВРИ` → `29-ТИ НОЕМВРИ`.
- `И` inside a name stays: `КИРИЛ И МЕТОДИЈ`, `МАРКС И ЕНГЕЛС` are one street each.
- The same location listed twice is labeled once.

Scoring ignores case, punctuation and repeated spaces, so `ДИМО ДИМОСКИ - НАРЕДНИКОТ` and
`ДИМО ДИМОСКИ-НАРЕДНИКОТ` count as the same name.

## partial

`true` when the text says only part of the location is affected:
- `ДЕЛ ОД`, `ДЕЛ`, `ДЕЛОТ` directly before it
- a sub-area qualifier: `КАЈ`, `ОКОЛУ`, `НА ИЗЛЕЗ`, `ВО БЛИЗИНА`, `ОД ... ДО ...`, `ПРЕД ВЛЕЗОТ`

`ДЕЛ ОД` before a plural (`ДЕЛ ОД УЛИЦИТЕ`, `ДЕЛ ОД КОРИСНИЦИТЕ НА`, `ДЕЛ ОД ПОТРОШУВАЧИТЕ`)
applies to the whole list that follows. Before a single item it applies to that item and to
anything joined to it with `И` (`ДЕЛ ОД С. СОКОЛАРЦИ И С. ВРБИЦА`: both partial). A comma ends it.

A road counts as a street when the affected objects are on it (`ВО БЛИЗИНА НА МОИНСКИ ПАТ`),
but not when it only gives a direction (`НА ПАТ ЗА С.ГОРОБИНЦИ`).

## numbers

House numbers, as strings: `БР.254` → `["254"]`, `ХРИСТО ТАТАРЧЕВ 23` → `["23"]`.
`БР.` followed by a number is always a house number, never a numbered street.
Ranges as `{"from": "10", "to": "30"}`; odd/even only as `"odd"` / `"even"`.

## in

For a street inside a named village, the village: `УЛ. 10 ... ВО КАДИНО` → `"in": "КАДИНО"`.
Leave it out when the street is in the town from `nasMesto`.

## uncertain

Set `"uncertain": true` with a short `note` when the right answer is not clear from the text.
These are the first ones to check in review. Labels still uncertain after review are left
out of scoring.
