"""Abstract base class for query-execution adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Interface every execution adapter must implement."""

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, Any]]:
        """Execute *query* against the backing store and return rows/docs."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by this adapter."""
        ...
