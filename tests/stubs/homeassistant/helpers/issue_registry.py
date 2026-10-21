"""Stub of homeassistant.helpers.issue_registry that records calls."""
from types import SimpleNamespace

ISSUES = {}


class IssueSeverity:
    WARNING = "warning"


def reset():
    ISSUES.clear()


def async_create_issue(hass, domain, issue_id, **kwargs):
    ISSUES[(domain, issue_id)] = SimpleNamespace(**kwargs)


def async_delete_issue(hass, domain, issue_id):
    ISSUES.pop((domain, issue_id), None)
