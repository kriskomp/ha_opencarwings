# Stale tests

Tests inherited from upstream that were written for an older, dict-based data model
(`OpenCarWingsAPI`, cars as plain dicts). Against the current code 39 of 44 fail, so the
suite could not gate a release. They are kept here for reference and are not collected
(see `collect_ignore_glob` in `tests/conftest.py`). Current tests live in `tests/`.
