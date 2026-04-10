class DummySyncRecord:
    """Lightweight stand-in for ``shopify.sync`` records used in tests."""

    def __init__(self) -> None:
        self.id = 1
        self.hard_throttle_count = 0
        self.total_count = 0
        self.updated_count = 0

    def ensure_not_canceled(self) -> None:
        """Mirror the real model API used by importer/exporter/deleter flows."""
        return
