# ADR 0003: Rule-based address parser, measured against a labeled set

- Status: Accepted
- Date: 2026-10-01

## Context

The `adresa` field of the power feed is free text: street lists, villages, house numbers,
abbreviations, typos, plus the reason for the work and substation codes. Alerts need structured
locations: kind, name, whether only part is affected, house numbers.

## Decision

1. **Labels before code.** 92 unique texts from two feed snapshots were labeled by hand following
   `docs/labeling-guidelines.md`, then reviewed by a native speaker. Labels nobody could settle are
   marked `uncertain` and left out of scoring.
2. **Fixed dev/test split.** A record is in `test` when the first 8 hex digits of its id are
   divisible by 4 (63 dev / 29 test). Rules were developed against dev errors only. The test split
   was scored once; it exposed one bug in an existing rule (a bracketed note marking part of a place),
   which was fixed. No rule was added for a test record.
3. **Rules, no model.** Normalize, split on `,` `;` `И` and sentence dots, find markers (`УЛ.`, `С.`,
   `НАСЕЛБА`, `ОПШТИНА`, ...), continue lists without markers, stop at the reason for the work and at
   companies, and apply the partial / house number / ordinal rules from the guidelines.
4. **Metrics.** Precision, recall and F1 on (kind, name) pairs, after removing case and punctuation;
   accuracy of `partial` and house numbers on the matched pairs. `vidituka eval-parser` prints them.
5. **Regression gate.** A test fails if overall F1 drops below 0.95, precision below 0.97 or partial
   accuracy below 0.99. Thresholds only go up.

## Results (labels power_v1)

| | records | precision | recall | F1 | partial |
|---|---|---|---|---|---|
| dev | 63 | 0.980 | 0.919 | 0.948 | 1.000 |
| test | 29 | 0.983 | 0.983 | 0.983 | 1.000 |
| all | 92 | 0.981 | 0.933 | 0.956 | 1.000 |
| Skopje only | 22 | 0.957 | 0.978 | 0.968 | 1.000 |

The test split scores higher than dev because it happens to contain fewer unmarked village lists;
with 29 records the difference is noise. The overall figure is the one to quote.

## Remaining errors

Almost all need knowledge that is not in the text:
- villages listed without `С.` and without a list to continue (`ЛЕСКОВИЦА, ПИПЕРЕВО, ...`)
- abbreviations of street names (`ВС БАТО` → `ВИДОЕ СМИЛЕВСКИ БАТО`) and of `Г.` (Горна or Голема)
- a descriptor glued to a name (`НОВО СЕЛО ШАРСКО`)

## Consequences

- The next improvement is a gazetteer: the official list of settlements and the OpenStreetMap street
  names, needed anyway for geocoding. Matching against it should fix most remaining errors, and the
  same labeled set will show whether it does.
- Precision matters more than recall for alerts (a wrong alert costs trust), which is why the rules
  drop unclear items instead of guessing.
- 92 records is a small set. It should grow from new feed snapshots, labeled the same way.
