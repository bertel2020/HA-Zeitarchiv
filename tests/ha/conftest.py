"""Gemeinsame Fixtures für die Tests gegen ein echtes Home Assistant.

Anders als die übrigen Tests eine Ebene höher, die einzelne Module ohne
homeassistant prüfen, laufen diese über pytest-homeassistant-custom-component:
Config-Flow, Setup und Unload werden tatsächlich ausgeführt. Nur der
HTTP-Client wird ersetzt — die Zeitarchiv-App läuft hier nicht.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator, Generator
from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Repo-Wurzel, damit `custom_components` als Paket auffindbar ist — für die
# Imports hier und für den Integrations-Loader von Home Assistant.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from custom_components.zeitarchiv.const import CONF_API_TOKEN, DOMAIN  # noqa: E402
from custom_components.zeitarchiv.queue_writer import ZeitarchivQueueWriter  # noqa: E402

TOKEN = "geheimer-token"
ENTRY_DATA = {
    CONF_NAME: "Produktivsystem",
    CONF_HOST: "zeitarchiv.local",
    CONF_PORT: 8127,
    CONF_API_TOKEN: TOKEN,
}
NOTICES = {"notices": [], "latest_backup": None, "demo_mode": False}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Ohne diese Freigabe lädt Home Assistant keine custom_components."""


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Ersetzt die drei HTTP-Aufrufe des Clients für Setup und Config-Flow.

    Gepatcht wird die Klasse selbst, nicht ein Import-Ort: __init__.py und
    config_flow.py bauen jeweils eigene Instanzen. Der Mock wird von allen
    Instanzen geteilt, damit Tests Fehler gezielt einspielen können."""
    client = MagicMock()
    client.get_notices.return_value = NOTICES
    with (
        patch(
            "custom_components.zeitarchiv.api.ZeitarchivClient.test_connection",
            client.test_connection,
        ),
        patch(
            "custom_components.zeitarchiv.api.ZeitarchivClient.get_notices",
            client.get_notices,
        ),
        patch(
            "custom_components.zeitarchiv.api.ZeitarchivClient.write_batch",
            client.write_batch,
        ),
    ):
        yield client


@pytest.fixture
def written(mock_client: MagicMock) -> list[dict]:
    """Alle an die App geschickten Events, in Sendereihenfolge."""
    events: list[dict] = []
    mock_client.write_batch.side_effect = events.extend
    return events


@pytest.fixture(autouse=True)
def fast_queue_writer() -> Generator[None]:
    """Kurze Batch- und Retry-Zeiten statt 5 s bzw. bis zu 60 s — sonst
    wartete jeder Schreibpfad-Test auf den produktiven Batch-Timeout."""
    with patch(
        "custom_components.zeitarchiv.ZeitarchivQueueWriter",
        partial(ZeitarchivQueueWriter, batch_timeout=0.02, retry_delays=(0.01,)),
    ):
        yield


async def wait_for_events(
    hass: HomeAssistant, written: list[dict], count: int
) -> None:
    """Wartet, bis der Queue-Writer-Thread `count` Events geschickt hat, und
    danach auf die Jobs, die er auf den Event-Loop zurückgibt (Wasserstand)."""
    async with asyncio.timeout(3):
        while len(written) < count:
            await asyncio.sleep(0.01)
    await hass.async_block_till_done()


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Zeitarchiv (Produktivsystem)",
        data=dict(ENTRY_DATA),
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def unload_after_test(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> AsyncGenerator[MockConfigEntry]:
    """Entlädt den Entry am Testende, falls er noch läuft.

    Pflicht für jeden Test, der den Entry einrichtet: Der Queue-Writer ist
    ein eigener Thread, und pytest-homeassistant-custom-component lässt
    jeden Test scheitern, der einen Thread zurücklässt."""
    yield config_entry
    if config_entry.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, mock_client: MagicMock, unload_after_test: MockConfigEntry
) -> MockConfigEntry:
    assert await hass.config_entries.async_setup(unload_after_test.entry_id)
    await hass.async_block_till_done()
    assert unload_after_test.state is ConfigEntryState.LOADED
    return unload_after_test
