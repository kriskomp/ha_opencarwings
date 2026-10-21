import os
import sys

# Ensure repo root is on sys.path so `custom_components` imports work
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure that tests/stubs is prepended to sys.path so our minimal "homeassistant" stub is importable
STUBS = os.path.join(os.path.dirname(__file__), "stubs")
if STUBS not in sys.path:
    sys.path.insert(0, STUBS)

# tests/stale/ holds the original upstream tests, written for an older dict-based
# data model; they no longer match the code and are not collected. See tests/stale/README.md.
collect_ignore_glob = ["stale/*"]
