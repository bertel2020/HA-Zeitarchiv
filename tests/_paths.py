"""Ein Ort für die Pfade der App — funktioniert in beiden Baum-Layouts.

Zeitarchiv wird in zwei Verzeichnisbäumen gepflegt: im Dev-Baum liegt `tests/`
eine Ebene ÜBER `addon/`, im Git-Repo liegt es NEBEN `app/`. Bis hierher trug
jede Testdatei diesen Unterschied selbst — 48-mal `sys.path.insert(...)` und
über hundert literale `"addon"`-Pfadsegmente, die beim Sync mechanisch
umgeschrieben werden mussten.

Das hatte einen Preis, der nichts mit Schreibarbeit zu tun hat: `diff -rq addon
HA-Apps/zeitarchiv` meldete dadurch IMMER alle Testdateien als verschieden und
war als Sync-Kontrolle wertlos. Eine echte inhaltliche Abweichung ginge in
diesem Rauschen unter — und Abweichungen gibt es: Testdateien, die nur in einem
der beiden Bäume liegen, fallen dort nicht auf.

Hier steht die Fallunterscheidung einmal. Danach sind beide Testbäume
byte-identisch und der Sync-Diff sagt wieder die Wahrheit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

#: Verzeichnis, das `app/` enthält — im Dev-Baum `addon/`, im Repo der Wurzel.
ADDON = ROOT / "addon" if (ROOT / "addon" / "app").is_dir() else ROOT

APP = ADDON / "app"
DOCS = ADDON / "docs"
TEMPLATES = APP / "templates"
STATIC = APP / "static"
APP_CSS = STATIC / "css" / "app.css"
#: Seitenlokales CSS, seit ZG-04 Schritt 3 aus den Templates herausgehoben.
PAGE_CSS = STATIC / "css" / "pages"
APP_JS = STATIC / "js"

# `from app.main import ...` muss in beiden Layouts funktionieren. Steht hier
# statt in conftest.py, damit auch ein einzeln aufgerufenes Testmodul es hat.
if str(ADDON) not in sys.path:
    sys.path.insert(0, str(ADDON))


def page_text(name: str) -> str:
    """Template samt dem CSS, das diese Seite mitbringt.

    Seit ZG-04 Schritt 3 stehen die seitenlokalen Regeln nicht mehr als
    <style>-Block im Template, sondern als static/css/pages/<seite>.css
    daneben. „Was diese Seite an CSS liefert" ist damit auf zwei Dateien
    verteilt — Tests, die eine solche Regel prüfen, meinen aber weiterhin
    beides zusammen. Deshalb hier einmal zusammengesetzt, statt in jedem
    betroffenen Test zwei Dateien von Hand zu lesen.
    """
    template = (TEMPLATES / name).read_text(encoding="utf-8")
    match = re.search(r"/static/css/pages/([a-z_]+\.css)", template)
    if match is None:
        return template
    return template + "\n" + (PAGE_CSS / match.group(1)).read_text(encoding="utf-8")
