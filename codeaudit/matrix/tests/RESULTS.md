# matrix analyzer regression results

## 2026-11-17 baseline

Command:

```bash
cd codeaudit
python3 -m matrix.tests.run_all
```

Fixture suite: **72/72 passed** (authz/authn + 10 extended endpoint analyzers +
4 repo analyzers + 5 original sink analyzers).

Demo regression:

| demo | endpoints | vuln recall | safe structural dispatch | N/A dispatch | unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| v1 | 12 | 1/1 = 100% | 20/21 = 95.24% | 0/1 | 1 |
| v2 | 12 | 10/10 = 100% | 11/12 = 91.67% | 0/1 | 1 |
| fresh-clinic | 10 | — | — | — | — |

Matrix finding distribution:

| demo | possible | impossible | unknown | total |
| --- | ---: | ---: | ---: | ---: |
| v1 | 28 | 143 | 33 | 204 |
| v2 | 27 | 143 | 34 | 204 |
| fresh-clinic | 22 | 144 | 4 | 170 |

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

## Rule change protocol

1. Add or update the relevant fixture under `fixtures/<vulnclass>/`.
2. Run `python3 -m matrix.tests.run_fixtures --vulnclass <name>`.
3. Run `python3 -m matrix.tests.run_all`.
4. If the demo baseline intentionally changes, run
   `python3 -m matrix.tests.run_regression --all --update-baseline`.
5. Record the reason and metric delta in this file.

Do not tune rules only against the demo labels. Demo v1/v2 are regression
corpora, not a blind holdout; the next step is a separately written v3.
