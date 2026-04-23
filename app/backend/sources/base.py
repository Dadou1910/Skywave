from abc import ABC, abstractmethod
from typing import Callable, Optional


# ── DataSource ────────────────────────────────────────────────────────────────
# Abstract base class that every data source must implement.
#
# A DataSource is responsible for one thing only: delivering raw parsed
# packets (plain Python dicts) to whoever is listening, via a callback.
#
# It knows nothing about normalisation, UI, or the database.
# It just connects to something, reads data, and calls on_packet().
#
# This design means the rest of the app can be written once and work
# with any source — mock, TCP, or Bluetooth — without any changes.
#
# ABC = Abstract Base Class. Any class that inherits from DataSource
# MUST implement all @abstractmethod methods or Python will refuse to
# instantiate it. This is how we enforce the contract.
class DataSource(ABC):

    def __init__(self):
        # The callback function that will be called with each new packet.
        # Set by the engine via set_callback() before start() is called.
        self._on_packet: Optional[Callable[[dict], None]] = None

    def set_callback(self, callback: Callable[[dict], None]) -> None:
        """Register the function to call when a new packet arrives."""
        self._on_packet = callback

    def _emit(self, packet: dict) -> None:
        """Call the registered callback with a packet. Safe to call from
        any thread — the engine handles thread-crossing via Qt signals."""
        if self._on_packet is not None:
            self._on_packet(packet)

    @abstractmethod
    def start(self) -> None:
        """Begin reading data. Should be non-blocking — start a background
        thread internally and return immediately."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop reading data and clean up all resources (sockets, threads,
        Bluetooth connections). Must be safe to call multiple times."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the source is currently connected and delivering
        data. Used by the UI to show connection status."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name shown in the UI, e.g. 'Mock (dev)'."""
        ...
