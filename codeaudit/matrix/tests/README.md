# matrix analyzer fixtures

Deterministic tests for structural analyzers. No PostgreSQL and no LLM.

## Run

```bash
cd codeaudit

# full deterministic suite: fixtures + demo regression + baseline check
python3 -m matrix.tests.run_all

# analyzer fixtures only
python3 -m matrix.tests.run_fixtures --all
python3 -m matrix.tests.run_fixtures --vulnclass authz
python3 -m matrix.tests.run_fixtures --vulnclass authz --case basic --rebuild

# demo regression only
python3 -m matrix.tests.run_regression --all --check
python3 -m matrix.tests.run_regression --all --update-baseline
```

The runner compiles the JavaParser callgraph sidecar on first use if
`codeaudit/tools/callgraph/CallGraphDump.class` does not exist.

See `RESULTS.md` for the current metric baseline and `BASELINE.json` for the
machine-readable snapshot.

## Layout

```text
fixtures/<vulnclass>/<case>/
  src/main/java/...       minimal source
  expected.json           expected structural result
```

`expected.json`:

```json
{
  "vulnclass": "authz",
  "scope": "endpoint",
  "endpoints": [
    {
      "method": "GET",
      "url": "/api/orders/{id}",
      "state": "possible",
      "gaps": ["ownership"],
      "sites": [{"file": "OrderService.java"}],
      "guards": [{"kind": "ownership"}],
      "subtype": "optional",
      "cwe": ["CWE-639"],
      "missing_contains": "optional"
    }
  ]
}
```

Repo-level fixtures use `"scope": "repo"` and no endpoints:

```json
{
  "vulnclass": "secrets",
  "scope": "repo",
  "state": "possible",
  "subtype": "hardcoded-credentials",
  "sites": [{"file": "application.yml"}]
}
```

Assertions are semantic: state, key evidence locations, subtype/CWE, guards,
gaps and missing text. Full JSON snapshots are intentionally not used.
