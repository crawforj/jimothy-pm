## What this changes and why

## Checklist

- [ ] `python -m unittest discover engine` passes
- [ ] `python manage.py check` passes
- [ ] `python manage.py makemigrations --check --dry-run` passes (or a
      migration is included)
- [ ] New engine logic has known-answer tests in `engine/tests/test_engine.py`
- [ ] New/changed UI copy lives in `core/phrases.py`, not hardcoded in a
      template
- [ ] If a template changed, I ran it locally and clicked through the
      affected page(s)

## Anything reviewers should focus on
