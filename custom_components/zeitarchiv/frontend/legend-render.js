// Legende mit Werten für Chart-Kacheln, getrennt von der Kachel im DOM.
// Aus dashboard-tiles.js herausgelöst (ROADMAP 1.49), damit dieselbe Legende
// auch die Lovelace-Karte zeichnen kann. Die Aufteilung:
//   buildStatsItem(s, points, name, color, ctx)   Kennzahlen einer Serie (Aktuell/Min/Max/Ø/Σ)
//   buildLegendItems({series, data, spec, multiYear})   alle Einträge eines Charts
//   renderLegendHtml(legend, hiddenSet)           Chips oder Tabelle als HTML-Text
// Nichts davon liest oder verändert DOM; Klick-Verdrahtung und Zwischenspeicher
// bleiben bei der jeweiligen Hülle (Kachel bzw. Karte).
// Braucht vorher: html-escape.js, number-format.js, i18n.js, chart-tile-render.js.
(() => {
  const {fmtCompactNumber, stateRows, switchOnDuration, withOpacity} = window.ChartTileRender;

  // "Ø"/"Σ" statt Text — dieselben Symbole wie chart_editor.js/entity_detail.js
  // (LEGEND_METRIC_OPTIONS dort), nur "Ø" stand hier schon vorher so; t("Summe")
  // war bis jetzt der einzige verbliebene Text-Ausreißer.
  const LEGEND_METRIC_LABELS = {last: t('Aktuell'), min: t('Min'), max: t('Max'), average: 'Ø', sum: 'Σ'};
  const METRIC_ORDER = ['last', 'min', 'max', 'average', 'sum'];

  // Kennzahlen einer Serie. Dieselbe Berechnung wie seriesStats() in
  // chart_editor.html (Min/Max/Ø/Summe/Aktuell).
  // ctx = {windowEnd, timeline, effectiveDecimals} — Zeitraumende (für
  // Zustände und Einschaltdauer), Rohwerte-Modus und Nachkommastellen je Serie.
  function buildStatsItem(s, points, name, color, ctx) {
    if (s.aggregation_type === 'state') {
      return {name, color, states: stateRows(s, ctx.windowEnd), last: '—', min: '—', max: '—', average: '—', sum: null};
    }
    const values = (points || []).map(p => p.value).filter(Number.isFinite);
    const minima = (points || []).map(p => Number.isFinite(p.min) ? p.min : p.value).filter(Number.isFinite);
    const maxima = (points || []).map(p => Number.isFinite(p.max) ? p.max : p.value).filter(Number.isFinite);
    const isDuration = s.aggregation_type === 'switch' && s.display_mode === 'time';
    const unit = s.unit ? ` ${s.unit}` : '';
    const formatted = value => isDuration ? NumberFormat.fmtDuration(value) : `${fmtCompactNumber(value, ctx.effectiveDecimals(s))}${unit}`;
    // Summe bei Zählern UND bei Schaltern sinnvoll (Bucket-Werte sind dort
    // bereits Einschaltsekunden) — siehe derselbe Kommentar in
    // chart_editor.html (seriesStats()). Im Zeitstrahl-/Rohwerte-Modus
    // (timeline=true) kommt die Summe stattdessen aus switchOnDuration(),
    // da die Punktwerte dann nur noch 0/1-Zustände sind.
    const isSwitch = s.aggregation_type === 'switch';
    const hasSum = s.aggregation_type === 'counter' || isSwitch;
    const sumValue = ctx.timeline && isSwitch ? switchOnDuration(points, ctx.windowEnd) : values.reduce((sum, v) => sum + v, 0);
    // Summe bei Schaltern ist immer eine Dauer in Sekunden — unabhängig
    // vom Anzeigemodus immer als h/m/s formatiert statt über
    // fmtCompactNumber()s generische 4-signifikante-Stellen-Rundung, die
    // bei größeren Sekundenwerten sichtbar ungenau wird (siehe
    // chart_editor.html/entity_detail.html, derselbe Fix).
    const sumFormatted = isSwitch ? NumberFormat.fmtDuration(sumValue) : formatted(sumValue);
    return {
      name,
      color,
      last: values.length ? formatted(values[values.length - 1]) : '—',
      min: minima.length ? formatted(Math.min(...minima)) : '—',
      max: maxima.length ? formatted(Math.max(...maxima)) : '—',
      average: values.length ? formatted(values.reduce((sum, v) => sum + v, 0) / values.length) : '—',
      sum: hasSum ? (values.length ? sumFormatted : '—') : null,
    };
  }

  // Punkt wie bisher, gestrichelt für die Ø-Linie der Langzeit-Kachel (wie
  // auf der Chart-Seite).
  function legendSwatch(item) {
    return item.dash
      ? `<span class="dash" style="border-color:${item.color};"></span>`
      : `<span class="dot" style="background:${item.color};"></span>`;
  }

  // Zustands-Entitäten (ROADMAP 1.29): statt Min/Max über Indizes die
  // Zustände der Zeile — Farbe, Name und (mit Statistik) Dauer · Anteil.
  function stateLegendValues(item, showStats) {
    return `<span class="values state-legend-values">${item.states.map(row =>
      `<span title="${escapeHtml(row.raw)}"><span class="dot state-dot" style="${row.swatch}"></span> ${escapeHtml(row.label)}`
      + (showStats ? ` <strong>${escapeHtml(row.text)}</strong>` : '') + '</span>').join('')}</span>`;
  }

  // Chip-Variante (Standard) — dieselben Chips/Kennzahlen wie chart_editor.html
  // (.chart-legend-item aus app.css), hier zusätzlich klickbar, anders als die
  // "static" (nicht umschaltbare) Variante auf entity_detail.html.
  function renderLegendChips(items, legendMetrics, showStats, hiddenSet) {
    return items.map(item => {
      // "+N Jahre" (Langzeit-Kachel): nur ein Hinweis, kein Serien-Umschalter.
      if (item.more) return `<span class="chart-legend-item is-more">${escapeHtml(item.more)}</span>`;
      if (item.states) {
        return `<span class="chart-legend-item static"><span class="name">${escapeHtml(item.name)}</span>`
             + `${stateLegendValues(item, showStats)}</span>`;
      }
      let values = '';
      if (showStats) {
        const parts = [];
        for (const key of METRIC_ORDER) {
          if (!legendMetrics.includes(key)) continue;
          if (key === 'sum' && item.sum === null) continue;
          parts.push(`<span>${LEGEND_METRIC_LABELS[key]} <strong>${escapeHtml(item[key])}</strong></span>`);
        }
        if (parts.length) values = `<span class="values">${parts.join('')}</span>`;
      }
      const inactive = hiddenSet.has(item.name) ? ' inactive' : '';
      return `<span class="chart-legend-item${inactive}" data-series="${escapeHtml(item.name)}" role="button" tabindex="0">`
           + legendSwatch(item)
           + `<span class="name">${escapeHtml(item.name)}</span>${values}</span>`;
    }).join('');
  }

  // Tabellen-Variante ("Legenden-Stil": Tabelle, Optionen-Menü der Chart-Seite)
  // — dieselbe Spalten-Darstellung wie .chart-legend-table in chart_editor.html
  // (table.dt compact). Zeilen sind wie die Chips klickbare Serien-Umschalter
  // (dieselbe .chart-legend-table-row-Klasse/CSS wie dort, siehe app.css).
  function renderLegendTable(items, legendMetrics, showStats, hiddenSet) {
    const cols = showStats ? METRIC_ORDER.filter(k => legendMetrics.includes(k)) : [];
    const headerCells = cols.map(key => `<th>${LEGEND_METRIC_LABELS[key]}</th>`).join('');
    const rows = items.filter(item => !item.more).map(item => {
      const cells = cols.map(key => `<td>${escapeHtml(key === 'sum' && item.sum === null ? '—' : item[key])}</td>`).join('');
      const inactive = hiddenSet.has(item.name) ? ' inactive' : '';
      if (item.states) {
        return `<tr class="chart-legend-table-row static"><td class="legend-name-col"><span class="name">${escapeHtml(item.name)}</span>`
             + `${stateLegendValues(item, showStats)}</td>${cells}</tr>`;
      }
      return `<tr class="chart-legend-table-row${inactive}" data-series="${escapeHtml(item.name)}" role="button" tabindex="0">`
           + `<td class="legend-name-col"><span class="legend-name-cell">`
           + legendSwatch(item)
           + `<span class="name">${escapeHtml(item.name)}</span></span></td>${cells}</tr>`;
    }).join('');
    return `<div class="tbl-wrap"><table class="dt compact chart-legend-table">`
         + `<thead><tr><th class="legend-name-col">Name</th>${headerCells}</tr></thead>`
         + `<tbody>${rows}</tbody></table></div>`;
  }

  // legend = {items, legendMetrics, showStats, style}; hiddenSet = Namen der
  // ausgeblendeten Serien.
  function renderLegendHtml(legend, hiddenSet) {
    const {items, legendMetrics, showStats, style} = legend;
    return style === 'table'
      ? renderLegendTable(items, legendMetrics, showStats, hiddenSet)
      : renderLegendChips(items, legendMetrics, showStats, hiddenSet);
  }

  // Die Legenden-Einträge eines Charts: je Serie einen, bei der Langzeit-Kachel das angezeigte Jahr und den Ø
  // (die übrigen Jahre als "+N Jahre"), beim Jahresvergleich je Entität das Jahr und das Vorjahr. Eine
  // Funktion für Kachel und Karte, damit beide dieselben Zeilen zeigen.
  // spec = readSpec(...) (Namen, Farben, Vergleich, Nachkommastellen), multiYear = tileMultiYear(...) oder null.
  function buildLegendItems({series, data, spec, multiYear}) {
    const {entityNames, colorFor, timeline, effectiveDecimals, compare} = spec;
    const ctx = {windowEnd: data.window_end, timeline, effectiveDecimals};
    const statsItem = (s, points, name, color) => buildStatsItem(s, points, name, color, ctx);
    if (multiYear) {
      // Entschieden: nur das angezeigte Jahr und der Ø, die übrigen Jahre als
      // "+N Jahre" (die Tabellen-Legende zeigt nur die beiden Zeilen).
      const s = series[0];
      const items = [statsItem(s, s.points, multiYear.series[0].name, multiYear.series[0].color)];
      if (multiYear.averageSeries) {
        items.push({
          ...statsItem(s, multiYear.averageSeries.monthly.filter(v => v != null).map(v => ({value: v})),
            multiYear.averageSeries.name, multiYear.averageSeries.color),
          dash: true,
        });
      }
      if (multiYear.hiddenYears > 0) items.push({more: t('+{n} Jahre', {n: multiYear.hiddenYears})});
      return items;
    }
    if (compare?.yearsCompare) {
      // Wie die Balkenpaare: je Entität angezeigtes Jahr und Vorjahr, die
      // Soll-Entität als eigene Zeile — Namen wie die Serien, damit das
      // Umschalten per Legende greift.
      // Jahr in der Zeitzone des Servers: der Browser kann in einer anderen stehen und um Silvester das Vorjahr liefern.
      const currentYear = window.ServerTime.parts(data.window_start || Date.now() / 1000).year;
      const items = [];
      series.forEach(s => {
        if (!s.compare_points) return;
        const color = colorFor(s.entity_id);
        const displayName = entityNames[s.entity_id] || s.friendly_name;
        if (s.entity_id === compare.target) { items.push(statsItem(s, s.points, displayName, color)); return; }
        items.push(statsItem(s, s.points, `${displayName} (${currentYear})`, color));
        // Die Vorjahresreihe läuft im Chart über das ganze Jahr; die Kennzahlen daneben gelten bis zum selben Tag wie das
        // laufende Jahr (compare_cut_points, nur bei Zählern und Schaltern), sonst stünde "bis heute" neben "komplett".
        items.push(statsItem(s, s.compare_cut_points || s.compare_points, `${displayName} (${currentYear - 1})`, withOpacity(color, 0.55)));
      });
      return items;
    }
    return series.map(s => statsItem(s, s.points, entityNames[s.entity_id] || s.friendly_name, colorFor(s.entity_id)));
  }

  window.LegendRender = {buildStatsItem, buildLegendItems, renderLegendHtml};
})();
