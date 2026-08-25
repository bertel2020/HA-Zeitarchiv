"""Hintergrund-Thread für Queue/Batch/Retry — Vorbild: die HA-Core-InfluxDB-Integration.

Bewusst ein eigener threading.Thread mit eigener queue.Queue, nicht ein
hass.async_add_executor_job pro Event: das Sammeln zu Batches und das
Backoff-Warten sollen den Event-Loop nie blockieren, und ein einzelner
lang laufender Worker ist einfacher korrekt zu halten als viele parallele
Executor-Jobs, die sich beim Senden überholen könnten.

Kein Import von homeassistant hier, damit sich Batching/Backoff/Drop-Verhalten
ohne laufende HA-Instanz testen lassen (siehe tests/test_queue_writer.py).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Protocol

from .api import ZeitarchivAuthError
from .const import BATCH_SIZE, BATCH_TIMEOUT, MAX_QUEUE_SIZE, RETRY_DELAYS

_LOGGER = logging.getLogger(__name__)

# Sentinel, um einen auf queue.get() wartenden Worker beim Herunterfahren zu wecken.
_STOP = object()


class WriteClient(Protocol):
    """Alles, was der Queue-Writer vom HTTP-Client braucht — für Fakes in Tests."""

    def write_batch(self, events: list[dict[str, Any]]) -> None: ...


class ZeitarchivQueueWriter:
    """Sammelt Events und schickt sie gebündelt über einen Hintergrund-Thread."""

    def __init__(
        self,
        client: WriteClient,
        *,
        max_queue_size: int = MAX_QUEUE_SIZE,
        batch_size: int = BATCH_SIZE,
        batch_timeout: float = BATCH_TIMEOUT,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        on_auth_failed: Callable[[], None] | None = None,
    ) -> None:
        self._client = client
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        self._retry_delays = retry_delays or (60.0,)
        # Callback statt eines homeassistant-Imports hier (siehe Modul-Docstring)
        # — __init__.py verdrahtet ihn mit entry.async_start_reauth, damit ein
        # von der App neu gesetzter/gelöschter Token (siehe Zeitarchiv-GUI,
        # Bereich "Verbindung") als normaler HA-Reauth-Hinweis auftaucht statt
        # nur endlos leise Batches im Log zu verlieren.
        self._on_auth_failed = on_auth_failed
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._abort_event = threading.Event()
        self._accepting = False
        self._dropped_count = 0
        # Für diagnostics.py — reine Beobachtungswerte, keine Steuerlogik
        # (deshalb einfache Attribute statt z. B. einer Lock-geschützten
        # Struktur; ein gelegentlich leicht veraltet gelesener Wert ist für
        # eine Diagnose-Momentaufnahme unkritisch).
        self._sent_count = 0
        self._last_success_ts: float | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._shutdown_event.clear()
        self._abort_event.clear()
        self._accepting = True
        self._thread = threading.Thread(
            target=self._run, name="zeitarchiv-queue-writer", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 15.0, drain_timeout: float = 2.0) -> bool:
        """Leert nach Möglichkeit die Queue und beendet den Worker zeitlich begrenzt.

        Kein blockierendes ``queue.put``: auch eine volle Queue kann den Aufrufer
        nicht festhalten. Ist die App erreichbar, wird auch ein noch nicht voller
        Batch vor dem Stopp geschrieben. Bei einer Störung beendet ``abort_event``
        nach der kurzen Drain-Phase sofort jede Backoff-Wartezeit. Nur ein bereits
        laufender HTTP-Aufruf kann noch bis zu seinem Client-Timeout dauern.
        """
        self._accepting = False
        self._shutdown_event.set()
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            pass
        if self._thread is None:
            return True

        started = time.monotonic()
        self._thread.join(timeout=min(max(0.0, drain_timeout), timeout))
        if self._thread.is_alive():
            self._abort_event.set()
            try:
                self._queue.put_nowait(_STOP)
            except queue.Full:
                pass
            remaining = max(0.0, timeout - (time.monotonic() - started))
            self._thread.join(timeout=remaining)
        return not self._thread.is_alive()

    def enqueue(self, event: dict[str, Any]) -> None:
        if not self._accepting and self._thread is not None:
            self._dropped_count += 1
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._dropped_count += 1
            if self._dropped_count == 1 or self._dropped_count % 100 == 0:
                _LOGGER.warning(
                    "Zeitarchiv-Warteschlange voll (%d Einträge) — Event für %s verworfen "
                    "(insgesamt %d verworfen)",
                    self._queue.maxsize,
                    event.get("entity_id", "?"),
                    self._dropped_count,
                )

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    @property
    def sent_count(self) -> int:
        """Erfolgreich geschickte Events seit Start dieses Writers (kein
        persistenter Zähler über einen HA-Neustart hinweg)."""
        return self._sent_count

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def last_success_ts(self) -> float | None:
        return self._last_success_ts

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        deadline = time.monotonic() + self._batch_timeout
        while not self._abort_event.is_set():
            timeout = max(0.0, deadline - time.monotonic())
            try:
                item = self._queue.get(timeout=timeout if timeout > 0 else 0.01)
            except queue.Empty:
                item = None

            if item is _STOP:
                item = None
            elif item is not None:
                batch.append(item)

            batch_full = len(batch) >= self._batch_size
            time_up = time.monotonic() >= deadline
            shutting_down = self._shutdown_event.is_set()
            if batch and (batch_full or time_up or shutting_down):
                if not self._flush(batch):
                    break
                batch = []
                deadline = time.monotonic() + self._batch_timeout

            if shutting_down and not batch and self._queue.empty():
                break

    def _flush(self, batch: list[dict[str, Any]]) -> bool:
        """Wiederholt einen Batch bis zum Erfolg oder bis zum expliziten Stopp."""
        attempt = 0
        auth_notified = False
        while not self._abort_event.is_set():
            delay = 0.0 if attempt == 0 else self._retry_delays[min(attempt - 1, len(self._retry_delays) - 1)]
            if delay and self._abort_event.wait(delay):
                return False
            try:
                self._client.write_batch(batch)
                self._sent_count += len(batch)
                self._last_success_ts = time.time()
                self._last_error = None
                return True
            except ZeitarchivAuthError as err:
                self._last_error = str(err)
                if not auth_notified:
                    _LOGGER.warning(
                        "Zeitarchiv-Token abgelehnt; Batch mit %d Events bleibt bis zur Reauth ausstehend: %s",
                        len(batch),
                        err,
                    )
                if not auth_notified and self._on_auth_failed is not None:
                    self._on_auth_failed()
                auth_notified = True
            except Exception as err:  # noqa: BLE001 — jeder andere Client-Fehler ist hier retry-würdig
                self._last_error = str(err)
                # Erster Fehler sowie danach nur noch periodisch loggen, damit
                # ein längerer App-Ausfall das HA-Log nicht flutet.
                if attempt == 0 or attempt % 10 == 0:
                    _LOGGER.warning(
                        "Zeitarchiv-Batch (%d Events) fehlgeschlagen (Versuch %d); "
                        "wird weiter versucht: %s",
                        len(batch),
                        attempt + 1,
                        err,
                    )
            attempt += 1
        return False
