"""Home-Assistant-Repairs für kritische Zeitarchiv-Meldungen.

Bewusst keine interaktiven Fix-Flows (is_fixable=False) — die eigentliche
Behebung (Backup erneut anstoßen, Aufbewahrung prüfen, Integration
aktualisieren) passiert in der Zeitarchiv-App bzw. via HACS, nicht in HA
selbst. Die Repair-Karte dient als Hinweis mit Handlungsanweisung im Text.

Bucket-A-Teilmenge der App-Meldungen (siehe notices.py dort) — nur
tatsächlich kritische Fälle. Für automatisierbare Dauerzustände (auch
weniger kritische) siehe binary_sensor.py, Bucket B."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

# housekeeping.host_disk_space_low: die warn-Stufe (<10% frei) reicht fürs
# binary_sensor-Bündel (siehe binary_sensor.py), erst die error-Stufe
# (<5% frei) rechtfertigt ein eigenes Repair-Issue. import.job_failed hatte
# hier früher denselben Platz (nur bei komplettem Fehlschlag, Status
# "partial" blieb außen vor) — entfernt, weil ein Import ohnehin interaktiv
# in der App ausgelöst wird und sein Ergebnis dort direkt sichtbar ist; die
# Integration bildete ihn nie als eigene Entity ab (kein binary_sensor), nur
# als einmalige Repair-Karte ohne Automatisierungswert.
_ERROR_ONLY_IDS = frozenset({"housekeeping.host_disk_space_low"})
_ALWAYS_IDS = frozenset({
    "backup.job_failed",
    "retention.job_failed",
    "housekeeping.inactive_entities_error",
    "integration.outdated",
})


def _relevant_notices(notices: list[dict]) -> dict[str, dict]:
    return {
        notice["id"]: notice
        for notice in notices
        if notice.get("id") in _ALWAYS_IDS
        or (notice.get("id") in _ERROR_ONLY_IDS and notice.get("severity") == "error")
    }


def async_sync_issues(hass: HomeAssistant, entry: ConfigEntry, notices: list[dict]) -> None:
    """Gleicht aktive Repair-Issues mit den aktuellen Meldungen ab — erzeugt
    neue, aktualisiert bestehende, entfernt nicht mehr zutreffende. Wird bei
    jedem Coordinator-Update aufgerufen (siehe __init__.py). issue_id trägt
    die entry_id, damit mehrere parallel eingerichtete Verbindungen (siehe
    __init__.py-Docstring: "Produktiv- und Testsystem") sich nicht
    überschreiben."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    previous_issue_ids: set[str] = entry_data.get("active_repair_issues", set())

    current = _relevant_notices(notices)
    current_issue_ids: set[str] = set()

    for notice_id, notice in current.items():
        issue_id = f"{entry.entry_id}_{notice_id}"
        current_issue_ids.add(issue_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=(
                ir.IssueSeverity.ERROR
                if notice.get("severity") == "error"
                else ir.IssueSeverity.WARNING
            ),
            translation_key=notice_id.replace(".", "_"),
            translation_placeholders={
                "connection": entry.title,
                "detail": notice.get("detail") or notice.get("title") or notice_id,
            },
        )

    for stale_issue_id in previous_issue_ids - current_issue_ids:
        ir.async_delete_issue(hass, DOMAIN, stale_issue_id)

    entry_data["active_repair_issues"] = current_issue_ids


def async_set_demo_mode_paused_issue(hass: HomeAssistant, entry: ConfigEntry, active: bool) -> None:
    """Eigenständiges Issue, NICHT über async_sync_issues()/die Notices-Liste
    (DEMO_MODUS_REAUTH_PLAN.md). Grund: während der Token abgelehnt wird,
    kann der ZeitarchivNoticesCoordinator /api/notices selbst nicht abrufen
    (derselbe Token) — der normale, notices-getriebene Repair-Weg ist in
    genau diesem Moment blockiert. Wird direkt aus queue_writer.py über
    on_demo_mode_detected/on_demo_mode_resolved ausgelöst, sobald ein
    abgelehnter Token per /api/health als "Ziel läuft im Demo-Modus" statt
    als echtes Tokenproblem erkannt wird bzw. sobald ein Batch danach
    wieder gelingt."""
    issue_id = f"{entry.entry_id}_demo_mode_paused"
    if active:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="demo_mode_paused",
            translation_placeholders={"connection": entry.title},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def async_clear_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entfernt alle noch offenen Repair-Issues eines Entries — beim Entladen/
    Entfernen der Verbindung, damit keine verwaisten Karten stehen bleiben."""
    # Nicht Teil von active_repair_issues (das führt nur async_sync_issues()
    # nach, siehe async_set_demo_mode_paused_issue() oben) — ir.async_delete_issue
    # ist ein No-op, falls das Issue gerade nicht aktiv ist, deshalb hier
    # unbedingt statt bedingt aufgerufen.
    ir.async_delete_issue(hass, DOMAIN, f"{entry.entry_id}_demo_mode_paused")
    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    if not entry_data:
        return
    for issue_id in entry_data.get("active_repair_issues", set()):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    entry_data["active_repair_issues"] = set()
