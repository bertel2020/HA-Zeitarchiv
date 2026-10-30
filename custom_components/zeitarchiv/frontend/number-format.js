// Zentrale Zahlenformatierung für die gesamte Oberfläche (Konzept: einheitliches
// Zahlenformat statt der bisherigen, gewachsenen Mischung aus Punkt-Dezimal
// (entity_detail.html, chart_editor.html) und deutschem Komma-Dezimal
// (dashboard-tiles.js, table-compute.js, statistik.html) — jede Datei rundete
// zwar nach derselben "4 signifikante Stellen, überflüssige Nullen weg"-Regel,
// gab das Ergebnis aber unterschiedlich aus.
//
// LOCALE ist bewusst die einzige Stelle, die ein Format kennt: es kommt aus
// window.ZA_FORMAT (de-DE / en-GB / en-US, Einstellung "Zahlen- und Datumsformat",
// siehe i18n.js und app/formats.py) — toLocaleString() liefert dafür automatisch das
// richtige Dezimal-/Tausendertrennzeichen, ohne dass die einzelnen
// Chart-/Tabellen-Dateien selbst etwas über das Format wissen müssen.
window.NumberFormat = (() => {
  const LOCALE = window.ZA_FORMAT;

  // Wie fmtValue()/fmtNum() bisher pro Datei: mit explizitem decimals immer
  // exakt auf diese Stellenzahl (auch mit anhängenden Nullen), sonst bis zu
  // 4 signifikante Stellen mit abgeschnittenen überflüssigen Nullen.
  function fmt(value, decimals) {
    if (value == null || Number.isNaN(value)) return '';
    if (decimals != null) {
      return value.toLocaleString(LOCALE, {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
    }
    if (value === 0) return '0';
    return Number(value.toPrecision(4)).toLocaleString(LOCALE);
  }

  // Gegenstück zu fmt() für Freitext-Zahleneingaben im Oberflächenformat (z. B.
  // Formel-Konstanten in Vergleichstabellen) — Dezimal-/Tausendertrennzeichen
  // werden aus LOCALE abgeleitet statt hart auf "," / "." zu setzen, damit ein
  // Formatwechsel automatisch mitzieht.
  const DECIMAL_SEP = (1.1).toLocaleString(LOCALE).replace(/\d/g, '');
  const THOUSANDS_SEP = (1000).toLocaleString(LOCALE).replace(/\d/g, '');

  function parse(text) {
    if (typeof text !== 'string') return text;
    let normalized = text.trim();
    if (THOUSANDS_SEP) normalized = normalized.split(THOUSANDS_SEP).join('');
    if (DECIMAL_SEP && DECIMAL_SEP !== '.') normalized = normalized.split(DECIMAL_SEP).join('.');
    return parseFloat(normalized);
  }

  // Sekunden als kompakte Dauer ("1h 29m", "45m", "12s") — für Schalter-
  // Entitäten (binary_sensor/switch/input_boolean) im Anzeigemodus "Zeit"
  // (Konzept: Einschaltdauer statt Rohsekunden), z. B. Anwesenheitssensoren.
  // Rundet auf ganze Sekunden, zeigt höchstens zwei Einheiten (h+m, nie h+m+s),
  // damit Achsen-/Tooltip-Beschriftungen kompakt bleiben.
  function fmtDuration(seconds) {
    if (seconds == null || Number.isNaN(seconds)) return '';
    const total = Math.round(Math.max(0, seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
    if (m > 0) return `${m}m`;
    return `${s}s`;
  }

  return {LOCALE, DECIMAL_SEP, THOUSANDS_SEP, fmt, parse, fmtDuration};
})();
