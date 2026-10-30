// Tooltip mehrerer Serien (chart_editor.js, dashboard-tiles.js): jede
// sichtbare Linien- und Balken-Serie zeigt ihren letzten bekannten Wert zum
// Cursor-Zeitpunkt.
//
// ECharts' trigger:'axis' listet nur Serien, die am Cursor einen eigenen Punkt
// haben — Entitäten mit unterschiedlichem Meldetakt (Temperatur alle 5 Min.,
// Luftfeuchtigkeit alle 30 Min., Ventil nur bei Änderung) fehlten deshalb
// zeitweise im Tooltip, ebenso Stundenbalken neben einer feineren Linie. Hier
// wird je Serie der letzte Punkt VOR oder AUF dem Cursor nachgeschlagen
// (Zeitachse, Tupel-Position 0 = ms-Zeitstempel, aufsteigend sortiert,
// Position 1 = Wert). Zeitstrahl, Vergleichs- und Durchschnittsserien bleiben
// bei ECharts' eigener Zeilenauswahl.
//
// Balken (bucket: true) gelten für ihren ganzen Zeitabschnitt: ein Stunden-
// balken ist bis zum nächsten Balken aktuell und wird erst danach als älter
// markiert. Linien gelten als älter, wenn sie dem jüngsten Linienpunkt um mehr
// als einen Meldetakt hinterherhinken.
window.TooltipHold = (() => {
  const MIN_STALE_MS = 60 * 1000;

  // Letzter Punkt mit x <= cursor, sonst null (Serie hat noch nicht begonnen).
  function lastAtOrBefore(data, cursor) {
    let lo = 0;
    let hi = data.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (data[mid][0] <= cursor) { found = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    return found === -1 ? null : data[found];
  }

  // Typischer Abstand der Punkte einer Serie (Median) — ein Wert gilt erst als
  // "älter", wenn er mehr als ein Meldetakt der dichtesten Serie zurückliegt,
  // sonst wäre bei jedem Hover zwischen zwei Punkten JEDE Zeile markiert.
  function medianGap(data) {
    const gaps = [];
    for (let i = 1; i < data.length; i++) {
      const gap = data[i][0] - data[i - 1][0];
      if (gap > 0) gaps.push(gap);
    }
    if (!gaps.length) return null;
    gaps.sort((a, b) => a - b);
    return gaps[Math.floor(gaps.length / 2)];
  }

  // marker wie ECharts' eigener, damit eine ergänzte Zeile nicht anders aussieht.
  const dot = color => `<span style="display:inline-block;margin-right:4px;border-radius:10px;width:10px;height:10px;background-color:${color};"></span>`;

  // allParams: ECharts-Params der Tooltip-Formatter-Funktion. holdSeries:
  // [{seriesIndex, name, color, data, bucket}] der beteiligten Serien (data wie
  // in der ECharts-Option, bucket: Balken). isVisible(name): ob die Serie in
  // der Legende an ist. Ergebnis: Params nach seriesIndex; beteiligte Serien
  // tragen zusätzlich holdAgeMs (> 0 nur, wenn ihr Wert merklich älter ist,
  // s. o.), holdX (Zeitstempel ihres Werts, ms) und holdBucket.
  function complete(allParams, holdSeries, isVisible) {
    const cursor = allParams.length ? allParams[0].axisValue : null;
    if (!holdSeries.length || typeof cursor !== 'number') return allParams;
    const lineGaps = holdSeries.filter(h => !h.bucket).map(h => medianGap(h.data)).filter(g => g != null);
    const lineThreshold = lineGaps.length ? Math.max(MIN_STALE_MS, Math.min(...lineGaps)) : MIN_STALE_MS;
    const byIndex = new Map(allParams.map(p => [p.seriesIndex, p]));
    const hits = [];
    holdSeries.forEach(h => {
      const point = isVisible(h.name) ? lastAtOrBefore(h.data, cursor) : null;
      if (!point || point[1] == null) { byIndex.delete(h.seriesIndex); return; }
      const previous = byIndex.get(h.seriesIndex);
      const param = {
        seriesIndex: h.seriesIndex,
        seriesName: h.name,
        marker: previous ? previous.marker : dot(h.color),
        axisValue: cursor,
        data: point,
        holdX: point[0],
        holdAgeMs: 0,
        holdBucket: !!h.bucket,
      };
      if (h.bucket) {
        // Eigene Bucket-Breite statt des Linien-Takts, s. o.
        const age = cursor - point[0];
        param.holdAgeMs = age > Math.max(MIN_STALE_MS, medianGap(h.data) ?? 0) ? age : 0;
      } else {
        hits.push(param);
      }
      byIndex.set(h.seriesIndex, param);
    });
    const newest = Math.max(...hits.map(p => p.holdX));
    hits.forEach(p => { if (newest - p.holdX > lineThreshold) p.holdAgeMs = newest - p.holdX; });
    return [...byIndex.values()].sort((a, b) => a.seriesIndex - b.seriesIndex);
  }

  // Zusatzzeile unter dem Wert einer veralteten Zeile: "10:30 · vor 5m".
  // fmtStamp(ms) liefert den Zeitpunkt (null: nur das Alter, wenn die Zeile den
  // Zeitpunkt schon an anderer Stelle trägt).
  function note(param, color, fmtStamp) {
    if (!param.holdAgeMs) return '';
    const age = t('vor {dauer}', {dauer: NumberFormat.fmtDuration(param.holdAgeMs / 1000)});
    const text = fmtStamp ? `${fmtStamp(param.holdX)} · ${age}` : age;
    return `<span style="display:block;font-size:0.85em;color:${color};">${text}</span>`;
  }

  return {complete, note};
})();
