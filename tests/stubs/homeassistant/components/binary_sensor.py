class BinarySensorEntity:
    """Minimal BinarySensorEntity stub for tests."""

    @property
    def is_on(self):
        return None

    @property
    def unique_id(self):
        return getattr(self, "_attr_unique_id", None)
