"""Which commands a car supports (``Car.supported_commands``, decided by its TCU type)."""
from __future__ import annotations

from typing import Any


def command_supported(car: Any, command_id: int) -> bool:
    """True when the car lists the command. An unknown list (no detail yet) counts as supported."""
    supported = getattr(car, "supported_commands", None)
    if not isinstance(supported, (list, tuple, set)):
        return True
    return command_id in supported
