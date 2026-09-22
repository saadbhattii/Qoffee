# Development

## Running tests

```bash
pip install -e ".[dev]"
pytest -m "not live"
```

## Debugging locally

```bash
python -m qoffee --check-config   # validate everything, contact nothing
python -m qoffee --dry-run        # fetch, decide, report: change nothing
```

## Exit codes

Exit codes are distinct so a red run tells you what broke without opening the log:

| Code | Meaning |
|---|---|
| `0` | Success, including "nothing tagged" |
| `1` | Configuration error, caught before IBM is contacted |
| `2` | IBM unreachable; no tags touched |
| `3` | A required notification channel failed; no tags touched |
| `4` | A job's tags can never be written; see the log for which |