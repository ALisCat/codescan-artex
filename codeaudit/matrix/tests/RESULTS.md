# matrix analyzer regression results

## 2026-11-17 baseline

Command:

```bash
cd codeaudit
python3 -m matrix.tests.run_all
```

Fixture suite: **85/85 passed** across 21 analyzers, including 16 SQL feature cases.

Demo regression:

| demo | endpoints | vuln recall | safe structural dispatch | N/A dispatch | unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| v1 | 12 | 1/1 = 100% | 17/21 = 80.95% | 0/1 | 1 |
| v2 | 12 | 10/10 = 100% | 8/12 = 66.67% | 0/1 | 1 |
| fresh-clinic | 10 | — | — | — | — |

Matrix finding distribution:

| demo | possible | impossible | unknown | total |
| --- | ---: | ---: | ---: | ---: |
| v1 | 18 | 153 | 33 | 204 |
| v2 | 18 | 153 | 33 | 204 |
| fresh-clinic | 13 | 153 | 4 | 170 |

## How to read the numbers

- **vuln recall** is the important safety metric: a labeled vulnerability must
  reach `possible` so the matrix dispatches it. v1/v2 are both 100%.
- **safe structural dispatch** is not the same as worker false positive.
  The current matrix intentionally does not exclude a direction because a guard
  is present; guards are evidence for the worker. A safe endpoint with a
  structural sink/resource is therefore still `possible` and will be dispatched.
  The worker is expected to return `clean` with positive evidence.
- **N/A dispatch** is expected to be 0 for this corpus. A non-zero value means
  an endpoint labeled N/A was structurally dispatched.
- **unknown** is a graph-completeness indicator, not a vulnerability verdict.
- **SQL feature model**: only raw SQL construction features (`${}`, dynamic
  concatenation, dynamic identifiers, raw wrapper args, unresolved SQL) are
  `possible`. Pure `#{}` / `?` + fixed template, `.eq()`, constant
  `orderBy("name")`, and constant `last("limit 1")` are not features and are
  not dispatched. Whitelists remain guards on an existing feature.
  In demo v1/v2 the SQL `possible` count dropped from 11/10 to 1/1; the
  remaining one is `report/appointments` with `${sort}`.

## Rule change protocol

1. Add or update the relevant fixture under `fixtures/<vulnclass>/`.
2. Run `python3 -m matrix.tests.run_fixtures --vulnclass <name>`.
3. Run `python3 -m matrix.tests.run_all`.
4. If the demo baseline intentionally changes, run
   `python3 -m matrix.tests.run_regression --all --update-baseline`.
5. Record the reason and metric delta in this file.

Do not tune rules only against the demo labels. Demo v1/v2 are regression
corpora, not a blind holdout; the next step is a separately written v3.
