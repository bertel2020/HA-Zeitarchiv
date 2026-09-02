"""Tests für custom_components/zeitarchiv/queue_writer.py — reine Python-Asserts, kein Framework.

Läuft gegen einen Fake-Client, damit kein echtes Add-on/HTTP nötig ist. Für
Retry-Tests werden Wartezeiten von null beziehungsweise wenigen Millisekunden
injiziert; die produktiven Intervalle bleiben davon unberührt.
"""

from __future__ import annotations

import threading
import time

import _pkg  # noqa: F401  (registriert die Namespace-Pakete als Seiteneffekt)
from custom_components.zeitarchiv.api import ZeitarchivAuthError
from custom_components.zeitarchiv.queue_writer import ZeitarchivQueueWriter


class FakeClient:
    """Zeichnet alle write_batch-Aufrufe auf; kann die ersten N Aufrufe fehlschlagen lassen."""

    def __init__(self, fail_first: int = 0, always_fail: bool = False) -> None:
        self.calls: list[list[dict]] = []
        self._fail_first = fail_first
        self._always_fail = always_fail
        self._lock = threading.Lock()
        self.event = threading.Event()

    def write_batch(self, events: list[dict]) -> None:
        with self._lock:
            attempt_no = len(self.calls) + 1
            self.calls.append(list(events))
        if self._always_fail or attempt_no <= self._fail_first:
            raise RuntimeError("simulierter Fehler")
        self.event.set()


class AuthFailingClient:
    """Lehnt jeden write_batch-Aufruf mit ZeitarchivAuthError ab (falscher/gelöschter Token)."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def write_batch(self, events: list[dict]) -> None:
        self.calls.append(list(events))
        raise ZeitarchivAuthError("Token abgelehnt")


def _wait(event: threading.Event, timeout: float = 2.0) -> None:
    assert event.wait(timeout), "Timeout beim Warten auf den Queue-Writer"


def test_flushes_when_batch_size_reached() -> None:
    client = FakeClient()
    writer = ZeitarchivQueueWriter(client, batch_size=3, batch_timeout=10)
    writer.start()
    try:
        for i in range(3):
            writer.enqueue({"entity_id": f"sensor.x{i}"})
        _wait(client.event)
        assert len(client.calls) == 1
        assert len(client.calls[0]) == 3
    finally:
        writer.stop()


def test_flushes_on_timeout_even_if_batch_not_full() -> None:
    client = FakeClient()
    writer = ZeitarchivQueueWriter(client, batch_size=100, batch_timeout=0.05)
    writer.start()
    try:
        writer.enqueue({"entity_id": "sensor.a"})
        writer.enqueue({"entity_id": "sensor.b"})
        _wait(client.event)
        assert len(client.calls) == 1
        assert len(client.calls[0]) == 2
    finally:
        writer.stop()


def test_retries_then_succeeds() -> None:
    client = FakeClient(fail_first=2)
    writer = ZeitarchivQueueWriter(
        client, batch_size=1, batch_timeout=10, retry_delays=(0, 0, 0)
    )
    writer.start()
    try:
        writer.enqueue({"entity_id": "sensor.a"})
        _wait(client.event)
        assert len(client.calls) == 3  # 1 Erstversuch + 2 Retries bis Erfolg
        assert all(call == [{"entity_id": "sensor.a"}] for call in client.calls)
    finally:
        writer.stop()


def test_keeps_batch_until_service_recovers() -> None:
    client = FakeClient(fail_first=5)
    writer = ZeitarchivQueueWriter(
        client, batch_size=1, batch_timeout=10, retry_delays=(0,)
    )
    writer.start()
    try:
        writer.enqueue({"entity_id": "sensor.a"})
        _wait(client.event)
        assert len(client.calls) == 6
        assert writer.sent_count == 1
    finally:
        writer.stop()


def test_exposes_stats_for_diagnostics() -> None:
    """Gegenstück zu diagnostics.py — sent_count/queue_size/last_success_ts/
    last_error müssen den tatsächlichen Verlauf widerspiegeln, sonst zeigt
    der Diagnose-Download in HA falsche Werte an."""
    client = FakeClient(fail_first=1)
    writer = ZeitarchivQueueWriter(
        client, batch_size=2, batch_timeout=10, retry_delays=(0, 0)
    )
    assert writer.sent_count == 0
    assert writer.last_success_ts is None
    assert writer.last_error is None
    writer.start()
    try:
        writer.enqueue({"entity_id": "sensor.a"})
        writer.enqueue({"entity_id": "sensor.b"})
        _wait(client.event)
        assert writer.sent_count == 2
        assert writer.last_success_ts is not None
        assert writer.last_error is None  # Erfolg löscht den inzwischen veralteten Fehler
        assert writer.queue_size == 0
    finally:
        writer.stop()


def test_auth_error_retries_and_calls_callback_once_per_batch() -> None:
    """Ein abgelehnter Token löst Reauth aus, der Batch bleibt aber erhalten."""
    client = AuthFailingClient()
    auth_failures = []
    writer = ZeitarchivQueueWriter(
        client,
        batch_size=1,
        batch_timeout=10,
        retry_delays=(0.01,),
        on_auth_failed=lambda: auth_failures.append(1),
    )
    writer.start()
    try:
        writer.enqueue({"entity_id": "sensor.a"})
        deadline = time.monotonic() + 2.0
        while not auth_failures and time.monotonic() < deadline:
            time.sleep(0.01)
        deadline = time.monotonic() + 2.0
        while len(client.calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(client.calls) >= 2
        assert len(auth_failures) == 1
    finally:
        writer.stop()


def test_drops_events_when_queue_is_full() -> None:
    client = FakeClient(always_fail=True)  # Worker läuft nicht mit, Queue bleibt voll
    writer = ZeitarchivQueueWriter(client, max_queue_size=2)
    # Thread absichtlich NICHT gestartet — die Queue soll deterministisch voll bleiben.
    writer.enqueue({"entity_id": "sensor.a"})
    writer.enqueue({"entity_id": "sensor.b"})
    writer.enqueue({"entity_id": "sensor.c"})  # verworfen, Queue ist voll
    assert writer.dropped_count == 1


def test_stop_flushes_partial_batch_when_service_is_reachable() -> None:
    client = FakeClient()
    writer = ZeitarchivQueueWriter(client, batch_size=100, batch_timeout=60)
    writer.start()
    writer.enqueue({"entity_id": "sensor.a"})
    assert writer.stop(timeout=2)
    assert client.calls == [[{"entity_id": "sensor.a"}]]


def test_stop_interrupts_long_retry_backoff() -> None:
    client = FakeClient(always_fail=True)
    writer = ZeitarchivQueueWriter(
        client, batch_size=1, batch_timeout=60, retry_delays=(60,)
    )
    writer.start()
    writer.enqueue({"entity_id": "sensor.a"})
    deadline = time.monotonic() + 2.0
    while not client.calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert client.calls
    started = time.monotonic()
    assert writer.stop(timeout=1, drain_timeout=0)
    assert time.monotonic() - started < 0.5


def _run_all() -> None:
    tests = [obj for name, obj in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
