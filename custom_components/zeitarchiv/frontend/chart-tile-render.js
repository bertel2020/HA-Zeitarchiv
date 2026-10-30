// Chart-Darstellung der Dashboard-Kacheln, getrennt von der Kachel im DOM.
// Aus dashboard-tiles.js herausgelöst, damit dieselbe Darstellung ohne die
// Kachel-Hülle (Drag&Drop, Legende, Größenwahl, Auto-Refresh) auch anderswo
// laufen kann, etwa in einer Lovelace-Karte. Die Aufteilung:
//   readSpec(ds)            Einstellungen aus einem data-*-artigen Objekt (reine Daten)
//   fetchChartData(spec, …) lädt die Reihen über /api/query-multi
//   prepareSeries / viewTypeFor   Auswahl der darstellbaren Serien und Ansicht
//   draw(chart, ctx)        baut die ECharts-Optionen und setzt sie
// Nichts davon liest oder verändert DOM außer dem übergebenen ECharts-Objekt.
(() => {
  // Dieselbe feste Farbpalette wie chart_editor.html — Kacheln und die volle
  // Chart-Seite sollen dieselbe Entität farblich konsistent zeigen.
  const PALETTE = Array.from({length: 8}, (_, i) =>
    getComputedStyle(document.documentElement).getPropertyValue(`--chart-${i + 1}`).trim()
  );
  const UI_FONT_SCALE = parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue('--font-scale')
  ) || 1;
  const scaledFont = size => Math.round(size * UI_FONT_SCALE * 10) / 10;
  // Wortgleich mit withOpacity() in chart_editor.js (Begründung dort: der
  // Tooltip-Marker ignoriert itemStyle.opacity).
  const withOpacity = (hex, opacity) => {
    const n = parseInt(hex.replace('#', ''), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${opacity})`;
  };
  const MONTH_LABELS = () => [t('Jan'), t('Feb'), t('Mär'), t('Apr'), t('Mai'), t('Jun'), t('Jul'), t('Aug'), t('Sep'), t('Okt'), t('Nov'), t('Dez')];
  // Kalendermonats-Buckets und Laufsumme — wortgleich mit monthlyBuckets()/
  // cumulate() in chart_editor.js (Begründungen dort).
  function monthlyBuckets(points, aggregationType) {
    const groups = Array.from({length: 12}, () => []);
    (points || []).forEach(point => {
      if (!Number.isFinite(point.value)) return;
      groups[new Date(point.ts * 1000).getMonth()].push(point.value);
    });
    return groups.map(values => {
      if (!values.length) return null;
      const sum = values.reduce((total, v) => total + v, 0);
      return aggregationType === 'standard' ? sum / values.length : sum;
    });
  }
  function cumulate(values) {
    let lastReal = -1;
    values.forEach((v, i) => { if (v != null) lastReal = i; });
    let sum = 0;
    return values.map((v, i) => {
      if (i > lastReal) return null;
      if (v != null) sum += v;
      return sum;
    });
  }

  // Vergleich, der mit dem Chart gespeichert ist (saved_charts.compare_settings,
  // data-compare-settings) — dieselben Regeln wie chart_editor.js: kein
  // Vergleich bei Zeitstrahl, Donut, Auflösung "Voll" oder gestapelten Balken
  // (dort ist der Knopf gesperrt), "Langzeit" nur bei Jahr/kalendarisch/genau
  // einer Entität, sonst wie im Editor "Vorjahr" (load()); "Vorjahr" mit
  // Laufsumme oder Soll zeichnet Monats-Balkenpaare (yearsCompareActive).
  const COMPARE_YEAR_RANGES = ['hour', 'day', 'week', 'month'];
  function tileCompare({compareSettings, range, continuous, entityIds, chartType, resolutionPreset, stacked}) {
    let settings = {};
    try { settings = JSON.parse(compareSettings || '{}') || {}; } catch (e) { settings = {}; }
    if (!settings.compare || ['timeline', 'donut', 'shares', 'changes', 'heatmap'].includes(chartType) || resolutionPreset === 'full'
        || (stacked && entityIds.length >= 2)) return null;
    let mode = settings.mode || 'previous';
    const longterm = mode === 'longterm' && range === 'year' && !continuous && entityIds.length === 1;
    if (mode === 'longterm' && !longterm) mode = 'previous';
    if (mode === 'year' && !COMPARE_YEAR_RANGES.includes(range)) mode = 'previous';
    const target = settings.target && entityIds.includes(settings.target) ? settings.target : '';
    const cumsum = !!settings.cumsum;
    return {
      mode, longterm, target, cumsum,
      years: settings.years ?? 5,
      average: settings.average ?? true,
      yearsCompare: mode === 'previous' && range === 'year' && (cumsum || !!target),
    };
  }

  // Durchschnitt der gezeichneten Werte, oder null wenn es keine gibt.
  // Wortgleich mit averageOf() in entity_detail.js/chart_editor.js — selbst
  // gerechnet statt über ECharts' eigenen Durchschnitts-Typ für markLine,
  // damit der Wert nicht davon abhängt, welche Punkte die Serie gerade führt.
  const averageOf = values => {
    const zahlen = values.filter(Number.isFinite);
    return zahlen.length ? zahlen.reduce((summe, v) => summe + v, 0) / zahlen.length : null;
  };
  // Gleitender Durchschnitt — wortgleich mit movingAverageWindow()/
  // movingAverage() in chart_editor.js (siehe dortiger Kommentar zur
  // Fensterbreite als Anteil statt fester Tageszahl).
  const movingAverageWindow = pointCount => Math.min(60, Math.max(3, Math.round(pointCount / 12)));
  const movingAverage = (points, windowPoints) => points.map((p, i) => {
    const start = Math.max(0, i - Math.floor(windowPoints / 2));
    const end = Math.min(points.length, i + Math.ceil(windowPoints / 2));
    const slice = points.slice(start, end).map(q => q.value).filter(Number.isFinite);
    return {ts: p.ts, value: slice.length ? slice.reduce((s, v) => s + v, 0) / slice.length : null};
  });
  const RESOLUTION_SECONDS = {
    hour: {medium: 5 * 60, coarse: 15 * 60},
    day: {medium: 30 * 60, coarse: 60 * 60},
    week: {medium: 6 * 60 * 60, coarse: 24 * 60 * 60},
    month: {medium: 24 * 60 * 60, coarse: 7 * 24 * 60 * 60},
    year: {medium: 30 * 24 * 60 * 60, coarse: 90 * 24 * 60 * 60},
    decade: {medium: 365 * 24 * 60 * 60, coarse: 2 * 365 * 24 * 60 * 60},
  };

  // ECharts stapelt auf einer Zeit-Achse nach INDEX in den Daten, nicht nach
  // Zeitstempel (nachgemessen mit ECharts 5.6: Serie B mit Beginn im April
  // landete auf Serie A vom Januar). Der Server liefert Buckets aber erst ab
  // dem ersten vorhandenen Wert — beginnen gestapelte Serien in
  // verschiedenen Perioden, rutscht die spätere nach links. Deshalb werden
  // alle Serien eines Stapels vor dem Zeichnen auf die Vereinigung ihrer
  // Zeitstempel gebracht; fehlende Stellen bekommen einen null-Wert (kein
  // Balken, keine erfundene "0"). Tooltips lassen null-Zeilen weg.
  // Gleiche Funktion in chart_editor.js.
  function padStackedSeries(seriesList) {
    const groups = new Map();
    seriesList.forEach(s => {
      if (!s.stack) return;
      if (!groups.has(s.stack)) groups.set(s.stack, []);
      groups.get(s.stack).push(s);
    });
    groups.forEach(list => {
      if (list.length < 2) return;
      const xs = new Set();
      list.forEach(s => s.data.forEach(p => xs.add(p[0])));
      const sorted = [...xs].sort((a, b) => a - b);
      list.forEach(s => {
        if (s.data.length === sorted.length) return;
        const byX = new Map(s.data.map(p => [p[0], p]));
        s.data = sorted.map(x => byX.get(x) || [x, null]);
      });
    });
  }

  // Ein rollierendes Fenster beginnt nicht an einer Tagesgrenze (z. B. 14:39).
  // Stunden- und Tagesbuckets, die daran hingen, lägen neben den Achsen-Ticks
  // (lokale Mitternacht). Deshalb auf die lokale Mitternacht abrunden, sofern
  // die Bucket-Breite den Tag teilt; "full" bleibt am Fensteranfang, damit alle
  // Punkte in Bucket 0 fallen. Gleiche Funktion in chart_editor.js.
  function bucketAnchor(windowStart, seconds, preset) {
    if (preset === 'full' || seconds < 3600 || 86400 % seconds !== 0) return windowStart;
    const midnight = new Date(windowStart * 1000);
    midnight.setHours(0, 0, 0, 0);
    return midnight.getTime() / 1000;
  }

  // Beginnt ein rollierendes Fenster mitten im Tag, liegt der erste Bucket
  // (Mitternacht) vor dem Achsenanfang: der Balken ragt über die y-Achse und
  // verdeckt deren Beschriftung. Die Achse beginnt dann eine halbe
  // Bucket-Breite vor dem ersten Balken, sodass er ganz im Diagramm liegt.
  // Gleiche Funktion in chart_editor.js.
  function axisMinForBars(seriesList, windowStartMs) {
    if (windowStartMs == null) return undefined;
    let min = windowStartMs;
    seriesList.filter(s => s.type === 'bar' && s.data && s.data.length > 1).forEach(s => {
      const xs = s.data.map(p => p[0]).filter(Number.isFinite).sort((a, b) => a - b);
      if (xs.length < 2 || xs[0] >= windowStartMs) return;
      let step = Infinity;
      for (let i = 1; i < xs.length; i++) if (xs[i] > xs[i - 1]) step = Math.min(step, xs[i] - xs[i - 1]);
      if (Number.isFinite(step)) min = Math.min(min, xs[0] - step / 2);
    });
    return min;
  }

  function resamplePoints(points, range, preset, aggregationType, windowStart) {
    const seconds = RESOLUTION_SECONDS[range] && RESOLUTION_SECONDS[range][preset];
    if (!seconds || !points.length || windowStart == null) return points;
    const anchor = bucketAnchor(windowStart, seconds, preset);
    const groups = new Map();
    points.forEach(point => {
      const bucket = Math.floor((point.ts - anchor) / seconds);
      const values = groups.get(bucket) || [];
      if (Number.isFinite(point.value)) values.push(point.value);
      groups.set(bucket, values);
    });
    return Array.from(groups.entries()).sort((a, b) => a[0] - b[0]).map(([bucket, values]) => ({
      ts: anchor + bucket * seconds,
      value: aggregationType === 'standard'
        ? values.reduce((sum, value) => sum + value, 0) / values.length
        : values.reduce((sum, value) => sum + value, 0),
    })).filter(point => Number.isFinite(point.value));
  }

  // Jede Datumsformatierung in dieser Datei läuft über Intl mit dieser einen Konstante;
  // das Format kommt aus der Einstellung (window.ZA_FORMAT, siehe i18n.js).
  const LOCALE = window.ZA_FORMAT;

  function fmtAxis(range, ts) {
    const d = new Date(ts * 1000);
    if (range === 'hour' || range === 'day') return d.toLocaleTimeString(LOCALE, window.ServerTime.withZone({hour: '2-digit', minute: '2-digit'}));
    if (range === 'week' || range === 'month') return d.toLocaleDateString(LOCALE, window.ServerTime.withZone({day: '2-digit', month: '2-digit'}));
    if (range === 'decade') return d.toLocaleDateString(LOCALE, window.ServerTime.withZone({year: 'numeric'}));
    return d.toLocaleDateString(LOCALE, window.ServerTime.withZone({month: 'short', year: 'numeric'}));
  }

  // Median-Abstand aufeinanderfolgender Zeitstempel — dieselbe Funktion wie in
  // chart_editor.html/entity_detail.html, hier für den Tooltip-Zeitstempel unten.
  function detectResolutionSeconds(points) {
    if (!points || points.length < 2) return null;
    const gaps = [];
    for (let i = 1; i < points.length; i++) {
      const gap = points[i].ts - points[i - 1].ts;
      if (gap > 0) gaps.push(gap);
    }
    if (!gaps.length) return null;
    gaps.sort((a, b) => a - b);
    return gaps[Math.floor(gaps.length / 2)];
  }

  // Gesamt-Einschaltdauer aus rohen AN/AUS-Zeitstempeln — dieselbe Paar-
  // bildung wie renderTileTimeline() beim Zeichnen der Zeitstrahl-Balken,
  // hier nur für die Legenden-Summe statt fürs Rendering. Identisch zu
  // switchOnDuration() in chart_editor.html/entity_detail.html.
  function switchOnDuration(points, windowEnd) {
    let total = 0;
    for (let i = 0; i < points.length; i++) {
      const start = points[i].ts;
      const end = i + 1 < points.length ? points[i + 1].ts : (windowEnd ?? start);
      if (points[i].value >= 0.5 && end > start) total += end - start;
    }
    return total;
  }

  // Tooltip-Zeitstempel richten sich nach der TATSÄCHLICHEN Bucket-Breite der
  // Daten, nicht nach dem Zeitraum-Namen — die Uhrzeit ist bei Tages-Buckets
  // oder gröber ohnehin immer Mitternacht, also reine Information ohne Wert.
  // Durchgehend über Intl (LOCALE) statt handgebauter Strings, damit sich
  // Datum/Uhrzeit/Wochentag mit einer künftigen Sprachumschaltung automatisch
  // anpassen. Der abgeschnittene Punkt hinter dem Wochentagskürzel
  // (".replace") gleicht nur einen ICU-Unterschied zwischen Engines aus
  // ("Mo" vs. "Mo.") — die Sprache/Reihenfolge selbst bleibt Intl überlassen.
  function fmtTooltipTimestamp(ms, bucketSeconds) {
    const d = new Date(ms);
    if (bucketSeconds == null || bucketSeconds < 86400) {
      return d.toLocaleString(LOCALE, window.ServerTime.withZone({day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'}));
    }
    if (bucketSeconds < 86400 * 25) {
      const weekday = d.toLocaleDateString(LOCALE, window.ServerTime.withZone({weekday: 'short'})).replace(/\.$/, '');
      const date = d.toLocaleDateString(LOCALE, window.ServerTime.withZone({day: '2-digit', month: '2-digit', year: 'numeric'}));
      return `${weekday}, ${date}`;
    }
    if (bucketSeconds < 86400 * 200) {
      return d.toLocaleDateString(LOCALE, window.ServerTime.withZone({month: 'long', year: 'numeric'}));
    }
    return d.toLocaleDateString(LOCALE, window.ServerTime.withZone({year: 'numeric'}));
  }

  // Langzeit-Kachel: Rechengrundlage wie der multiYear-Getter in
  // chart_editor.js (Kalendermonate je Jahr, Ø je Monat über die Vorjahre),
  // ohne Tabelle und Jahreswerte — die gibt es nur auf der Chart-Seite.
  // Entschieden: eine 1×1-Kachel zeichnet nur das angezeigte Jahr und den Ø.
  function tileMultiYear(s, data, compare, {small, color, inkMuted}) {
    const agg = s.aggregation_type;
    const mean = values => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
    const currentYear = data.window_start ? new Date(data.window_start * 1000).getFullYear() : new Date().getFullYear();
    const running = (data.is_current ?? true) && data.window_end != null;
    const cutMonth = running ? new Date(data.window_end * 1000 - 1).getMonth() : null;
    const years = [
      {year: currentYear, monthly: monthlyBuckets(s.points, agg), isCurrent: true},
      ...s.years.map(y => ({year: y.year, monthly: monthlyBuckets(y.points, agg), isCurrent: false})),
    ];
    const previous = years.slice(1);
    const total = years.length;
    // Farbe je Alter abgestuft — wortgleich mit multiYearColor() in chart_editor.js.
    const yearColor = index => {
      if (index === 0) return color;
      const steps = Math.max(total - 1, 1);
      return withOpacity(color, total === 2 ? 0.55 : 0.75 - 0.5 * (index - 1) / Math.max(steps - 1, 1));
    };
    const shown = small ? years.slice(0, 1) : years;
    const averageSeries = compare.average && previous.length ? {
      name: t('Ø {from}–{to}', {from: previous[previous.length - 1].year, to: previous[0].year}),
      monthly: Array.from({length: 12}, (_, m) => mean(previous.map(y => y.monthly[m]).filter(v => v != null))),
      color: inkMuted,
    } : null;
    return {
      cutMonth,
      series: shown.map((y, i) => ({...y, name: String(y.year), color: yearColor(i)})),
      averageSeries,
      // Jahre, die die Legende nicht einzeln nennt (nur bei mehr als 1×1 —
      // dort sind sie gezeichnet, aber nicht benannt).
      hiddenYears: small ? 0 : total - 1,
    };
  }

  function tileValueFormatter(s, decimals) {
    const isDuration = s.aggregation_type === 'switch' && s.display_mode === 'time';
    return v => v == null ? '—' : (isDuration ? NumberFormat.fmtDuration(v) : `${fmtCompactNumber(v, decimals)}${s.unit ? ' ' + escapeHtml(s.unit) : ''}`);
  }

  // Gemeinsamer Rahmen der beiden Monats-Renderpfade unten: feste
  // Jan–Dez-Achse statt Zeitachse, Tooltip mit den nicht leeren Zeilen.
  function tileMonthOption(echartsSeries, yAxis, {animation, style, borderColor, inkFaint, inkMuted, surface, hiddenSet, orderRows}) {
    const legendSelected = {};
    echartsSeries.forEach(x => { legendSelected[x.name] = !hiddenSet || !hiddenSet.has(x.name); });
    return {
      animation,
      textStyle: {fontFamily: style.getPropertyValue('--font-mono')},
      grid: {left: 6, right: 6, top: 10, bottom: 20, containLabel: true},
      xAxis: {
        type: 'category', data: MONTH_LABELS(),
        axisLabel: {fontSize: scaledFont(10), color: inkFaint, hideOverlap: true},
        axisLine: {lineStyle: {color: borderColor}}, axisTick: {show: false},
      },
      yAxis,
      tooltip: {
        trigger: 'axis',
        backgroundColor: surface,
        borderColor,
        textStyle: {color: inkMuted, fontFamily: style.getPropertyValue('--font-mono'), fontSize: scaledFont(12)},
        formatter: (allParams) => {
          const params = orderRows(allParams.filter(p => p.value != null));
          if (!params.length) return '';
          const rows = params.map(p => {
            const fmt = echartsSeries[p.seriesIndex]?.valueFormatter || (v => String(v));
            return `<div style="display:flex;justify-content:space-between;gap:14px;">`
                 + `<span>${p.marker}${escapeHtml(p.seriesName)}</span><strong style="margin-left:8px;">${fmt(p.value)}</strong></div>`;
          }).join('');
          return `<div style="margin-bottom:4px;color:${inkFaint};">${escapeHtml(allParams[0]?.axisValue ?? '')}</div>${rows}`;
        },
        appendToBody: true,
      },
      legend: {show: false, data: echartsSeries.map(x => x.name), selected: legendSelected},
      series: echartsSeries.map(({valueFormatter, ...rest}) => rest),
    };
  }

  function renderTileMultiYear(chart, my, s, opts) {
    const format = tileValueFormatter(s, opts.effectiveDecimals(s));
    // Älteste zuerst, damit das angezeigte Jahr obenauf liegt (wie im Editor).
    const echartsSeries = my.series.map(y => ({
      name: y.name,
      type: 'line',
      data: y.monthly.map((v, m) => (y.isCurrent && m === my.cutMonth && v != null
        ? {value: v, symbol: 'emptyCircle', symbolSize: 7}
        : v)),
      lineStyle: {color: y.color, width: y.isCurrent ? 2.5 : 1.2},
      itemStyle: {color: y.color},
      symbol: y.isCurrent ? 'circle' : 'none',
      symbolSize: 4,
      z: y.isCurrent ? 4 : 2,
      valueFormatter: format,
    })).reverse();
    if (my.averageSeries) {
      echartsSeries.push({
        name: my.averageSeries.name,
        type: 'line',
        data: my.averageSeries.monthly,
        lineStyle: {color: my.averageSeries.color, type: 'dashed', width: 1.8},
        itemStyle: {color: my.averageSeries.color},
        symbol: 'none',
        z: 5,
        valueFormatter: format,
      });
    }
    const yAxis = {
      type: 'value', scale: true,
      axisLabel: {fontSize: scaledFont(10), color: opts.inkFaint, formatter: v => fmtCompactNumber(v, opts.effectiveDecimals(s))},
      axisLine: {show: false}, axisTick: {show: false},
      splitLine: {lineStyle: {color: opts.borderColor, type: 'dashed'}},
    };
    // Entschieden: alle gezeichneten Jahre, das neueste oben, der Ø zuletzt.
    const orderRows = params => {
      const average = params.filter(p => my.averageSeries && p.seriesName === my.averageSeries.name);
      return [...params.filter(p => !average.includes(p)).reverse(), ...average];
    };
    chart.setOption(tileMonthOption(echartsSeries, yAxis, {...opts, orderRows}), true);
  }

  // "Vorjahr" mit Laufsumme oder Soll: Monats-Balkenpaare wie
  // renderYearsCompare() in chart_editor.js — Laufsumme auf eigener,
  // unsichtbarer Achse je Einheit, Soll als gepunktete Linie. Ohne
  // Achsennamen: dafür ist in der Kachel kein Platz.
  function renderTileYearsCompare(chart, series, compare, data, opts) {
    const {entityNames, colorFor, effectiveDecimals} = opts;
    const isDurationSeries = s => s.aggregation_type === 'switch' && s.display_mode === 'time';
    const axisUnit = s => isDurationSeries(s) ? ' duration' : s.unit;
    const hasCompare = s => !!s.compare_points;
    const isSoll = s => !!compare.target && s.entity_id === compare.target;
    const currentYear = data.window_start ? new Date(data.window_start * 1000).getFullYear() : new Date().getFullYear();
    const units = [...new Set(series.filter(hasCompare).map(axisUnit))];
    const cumUnits = compare.cumsum ? [...new Set(series.filter(s => hasCompare(s) && !isSoll(s)).map(axisUnit))] : [];
    const barUnits = new Set(series.filter(s => hasCompare(s) && !isSoll(s)).map(axisUnit));
    const unitDecimals = new Map();
    series.forEach(s => {
      const d = effectiveDecimals(s);
      if (d == null) return;
      const current = unitDecimals.get(axisUnit(s));
      if (current == null || d < current) unitDecimals.set(axisUnit(s), d);
    });
    let visiblePos = 0;
    const yAxis = [...units, ...cumUnits].map((u, i) => {
      const hidden = i >= units.length || !barUnits.has(u);
      const pos = hidden ? 0 : visiblePos++;
      const decimals = unitDecimals.get(u);
      return {
        type: 'value',
        show: !hidden,
        position: pos % 2 === 0 ? 'left' : 'right',
        offset: Math.floor(pos / 2) * 46,
        min: value => Math.min(0, value.min),
        max: value => Math.max(0, value.max),
        axisLine: {show: false}, axisTick: {show: false},
        splitLine: {show: !hidden, lineStyle: {color: opts.borderColor, type: 'dashed'}},
        axisLabel: {
          show: !hidden, fontSize: scaledFont(10), color: opts.inkFaint,
          formatter: v => u === ' duration' ? NumberFormat.fmtDuration(v) : fmtCompactNumber(v, decimals),
        },
      };
    });
    const cumAxisIndex = u => units.length + cumUnits.indexOf(u);
    const echartsSeries = [];
    series.forEach(s => {
      if (!hasCompare(s)) return;
      const color = colorFor(s.entity_id);
      const displayName = entityNames[s.entity_id] || s.friendly_name;
      const valueFormatter = tileValueFormatter(s, unitDecimals.get(axisUnit(s)));
      if (isSoll(s)) {
        echartsSeries.push({
          name: displayName, type: 'line', yAxisIndex: units.indexOf(axisUnit(s)),
          data: monthlyBuckets(s.points, s.aggregation_type),
          lineStyle: {type: 'dotted', width: 2, color}, itemStyle: {color}, symbol: 'none', z: 3, valueFormatter,
        });
        return;
      }
      [
        {year: currentYear, points: s.points, opacity: 1},
        {year: currentYear - 1, points: s.compare_points, opacity: 0.55},
      ].forEach(({year, points, opacity}) => {
        const monthly = monthlyBuckets(points, s.aggregation_type);
        echartsSeries.push({
          name: `${displayName} (${year})`, type: 'bar', yAxisIndex: units.indexOf(axisUnit(s)), barGap: '20%',
          barMaxWidth: 14, data: monthly, itemStyle: {color: withOpacity(color, opacity), borderRadius: [2, 2, 0, 0]}, valueFormatter,
        });
        if (compare.cumsum) {
          echartsSeries.push({
            name: t('{name} ({year}) kumuliert', {name: displayName, year}), type: 'line',
            yAxisIndex: cumAxisIndex(axisUnit(s)), data: cumulate(monthly),
            lineStyle: {type: 'dashed', width: 2, color: withOpacity(color, opacity)},
            itemStyle: {color: withOpacity(color, opacity)}, symbol: 'none', z: 4, valueFormatter,
          });
        }
      });
    });
    chart.setOption(tileMonthOption(echartsSeries, yAxis, {...opts, orderRows: params => params}), true);
  }

  // Kompakter Zeitstrahl für eine Kachel — eine Kategorie-Zeile je Entität,
  // dieselbe Balken-Technik wie renderTimelineMulti() in chart_editor.html,
  // hier nur mit den kleineren Kachel-Schriftgrößen/Abständen. Ohne
  // Zeilen-Beschriftung (der Name steht schon in der Kachel-Legende, siehe
  // renderTile()) — bei mehreren Zeilen in einer kleinen Kachel wäre dafür
  // ohnehin kaum Platz.
  // Dauer und Anteil je Zustand einer Zustands-Serie — für Legende und
  // Donut. Rohwechsel (bis zur Woche, Zeitstrahl) und Server-Anteile (ab dem
  // Monat) ergeben dieselbe Form; dieselbe Rechnung wie stateRowsFor() in
  // pages/chart_editor.js.
  function stateRows(s, windowEnd) {
    // Ohne Rohwechsel (Rohabfrage über der Grenze) aus den Spalten vom Server.
    const buckets = s.chart_type === 'shares'
      ? StateEntities.bucketsFromShares(s.points || [])
      : (!(s.points || []).length && s.columns
        ? StateEntities.bucketsFromShares(s.columns.map(([ts, states]) => ({ts, states})))
        : StateEntities.bucketsFromSegments(StateEntities.segments(s.points || [], windowEnd), () => 0, () => Infinity));
    return StateEntities.totals(buckets, s.states).map(row => ({
      ...row,
      label: StateEntities.label(s.states, row.idx),
      raw: StateEntities.raw(s.states, row.idx),
      swatch: StateEntities.swatchStyle(row.idx),
      text: `${NumberFormat.fmtDuration(row.seconds)} · ${StateEntities.fmtShare(row.share)}`,
    }));
  }

  // Anteile oder Wechsel je Zustands-Entität, wie im Chart-Editor.
  function renderTileStateBars(chart, series, entityNames, data, range, mode, animation) {
    const rows = series.filter(s => s.aggregation_type === 'state').map(s => ({
      name: entityNames[s.entity_id] || s.friendly_name,
      states: s.states,
      buckets: StateEntities.bucketsForSeries(s, range, data.window_end),
    }));
    chart.setOption({
      ...StateEntities.barPanels(rows, {mode, range, windowStart: data.window_start, periodEnd: data.period_end ?? data.window_end}),
      animation,
    }, true);
  }

  // Heatmap je Zustands-Entität, wie im Chart-Editor, nur kompakt.
  function renderTileStateHeatmap(chart, series, entityNames, animation, heatmapStates) {
    const rows = series
      .filter(s => s.aggregation_type === 'state' && s.cells)
      .map(s => ({
        name: entityNames[s.entity_id] || s.friendly_name,
        states: s.states,
        cells: s.cells,
        idx: StateEntities.heatmapIndexFor(s.cells, s.states, heatmapStates[s.entity_id]),
      }))
      .filter(row => row.idx !== null);
    if (!rows.length) {
      chart.clear();
      return;
    }
    chart.setOption({...StateEntities.heatmapPanels(rows, {compact: true}), animation}, true);
  }

  function renderTileTimeline(chart, series, entityNames, data, range, animation, style, borderColor, inkFaint, surface, colorFor) {
    const categories = series.map(s => entityNames[s.entity_id] || s.friendly_name);
    const items = [];
    const pattern = StateEntities.unavailablePattern();
    // Zustände: ein Band je Abschnitt, Farbe nach Zustand (wie im Chart-Editor), bei
    // zu vielen Abschnitten für die Breite je Bildpunkt eine Spalte mit den Anteilen.
    const stateRows = series
      .map((s, catIndex) => ({catIndex, points: s.points, columns: s.columns, dt: s.dt, aggregation_type: s.aggregation_type}))
      .filter(row => row.aggregation_type === 'state');
    const stateTimeline = StateEntities.stateTimelineItems(
      stateRows, data.window_start, data.period_end ?? data.window_end, data.window_end,
      Math.max(60, Math.round(chart.getWidth() - 10)), pattern
    );
    const timelineParts = stateTimeline.parts;
    items.push(...stateTimeline.items);
    series.forEach((s, catIndex) => {
      if (s.aggregation_type === 'state') return;
      const color = colorFor(s.entity_id);
      const points = s.points || [];
      for (let i = 0; i < points.length; i++) {
        const start = points[i].ts;
        const end = i + 1 < points.length ? points[i + 1].ts : (data.window_end ?? start);
        if (points[i].value >= 0.5 && end > start) {
          items.push([catIndex, start * 1000, end * 1000, color]);
        }
      }
    });
    chart.setOption({
      animation,
      textStyle: {fontFamily: style.getPropertyValue('--font-mono')},
      grid: {left: 4, right: 6, top: 10, bottom: 20, containLabel: true},
      xAxis: {
        type: 'time',
        min: data.window_start != null ? data.window_start * 1000 : undefined,
        max: (data.period_end ?? data.window_end) != null ? (data.period_end ?? data.window_end) * 1000 - 1000 : undefined,
        boundaryGap: [0, 0],
        interval: ['week', 'month'].includes(range) ? 24 * 60 * 60 * 1000 : undefined,
        axisLabel: {
          formatter: v => {
            const rawPeriodEndMs = (data.period_end ?? data.window_end) != null ? (data.period_end ?? data.window_end) * 1000 : null;
            if (rawPeriodEndMs != null && v >= rawPeriodEndMs) return '';
            return fmtAxis(range, v / 1000);
          },
          fontSize: scaledFont(10), color: inkFaint, hideOverlap: true,
        },
        axisLine: {lineStyle: {color: borderColor}},
        axisTick: {show: false},
        splitLine: {show: false},
      },
      yAxis: {
        type: 'category', data: categories.map(() => ''), inverse: true,
        axisLine: {show: false}, axisTick: {show: false}, splitLine: {show: false},
      },
      tooltip: {
        trigger: 'item',
        backgroundColor: surface,
        borderColor,
        textStyle: {color: style.getPropertyValue('--ink-muted').trim(), fontFamily: style.getPropertyValue('--font-mono'), fontSize: scaledFont(12)},
        formatter: p => {
          const [catIndex, startMs, endMs, , idx, partsIndex] = p.value;
          const pad = n => String(n).padStart(2, '0');
          const fmtTime = ms => { const t = window.ServerTime.parts(ms / 1000); return `${pad(t.hour)}:${pad(t.minute)}`; };
          const span = `${fmtTime(startMs)}–${fmtTime(endMs)} · <strong>${NumberFormat.fmtDuration((endMs - startMs) / 1000)}</strong>`;
          const s = series[catIndex];
          if (!s || s.aggregation_type !== 'state') return `${escapeHtml(categories[catIndex])}<br>${span}`;
          if (partsIndex >= 0) {
            // Spalte über mehrere Tage: Datum dazu, in Serverzeit wie überall auf der Kachel.
            const stamp = ms => { const t = window.ServerTime.parts(ms / 1000); return `${pad(t.day)}.${pad(t.month)}. ${pad(t.hour)}:${pad(t.minute)}`; };
            return StateEntities.condensedTooltip(timelineParts[partsIndex], startMs, endMs, s.states, stamp, escapeHtml(categories[catIndex]));
          }
          return `${escapeHtml(categories[catIndex])}<br><strong>${escapeHtml(StateEntities.label(s.states, idx))}</strong><br>${span}`;
        },
        appendToBody: true,
      },
      series: [{
        type: 'custom',
        renderItem: (params, api) => {
          const categoryIndex = api.value(0);
          const start = api.coord([api.value(1), categoryIndex]);
          const end = api.coord([api.value(2), categoryIndex]);
          const height = api.size([0, 1])[1] * 0.6;
          const rectShape = echarts.graphic.clipRectByRect(
            {x: start[0], y: start[1] - height / 2, width: Math.max(end[0] - start[0], api.value(4) != null ? 1 : 0), height},
            {x: params.coordSys.x, y: params.coordSys.y, width: params.coordSys.width, height: params.coordSys.height}
          );
          // Verdichtete Spalte: die Anteile der Zustände als Schichten.
          if (rectShape && api.value(5) >= 0) {
            return StateEntities.condensedShape(timelineParts[api.value(5)], rectShape, idx => StateEntities.fill(idx, pattern));
          }
          return rectShape && {type: 'rect', shape: rectShape, style: {fill: api.value(3)}};
        },
        encode: {x: [1, 2], y: 0},
        data: items,
      }],
    }, true);
  }

  // Zentral in static/js/number-format.js (window.NumberFormat) — dieselbe
  // Formatierung wie überall sonst in der Oberfläche, siehe Kommentar dort.
  const fmtCompactNumber = NumberFormat.fmt;

  // Donut statt Zeitverlauf ("Darstellungsart", Optionen-Menü der Chart-
  // Seite) — Kachel-Parität zu chart_editor.js renderDonut(): ein Anteil je
  // Serie aus GENAU EINEM aggregierten Wert (aggregation: Summe/Durchschnitt/
  // Letzter Wert der bereits geladenen Punkte), keine Zeitachse. Dieselbe
  // Radius-/Emphasis-Konfiguration wie #storage-pie (statistik.js) und
  // .edash-share-donut (energiedashboard.js) — label:show:false, weil die
  // Namen schon in der .dtile-legend-Zeile stehen (renderTile() baut sie VOR
  // diesem Zweig, siehe renderLegend()-Aufruf dort, unverändert wiederverwendet).
  // Zustände: ein Donut je Zustands-Entität nebeneinander, wie
  // renderStateDonuts() in pages/chart_editor.js.
  function renderTileStateDonuts(chart, series, entityNames, windowEnd, style, surface) {
    const rows = series.filter(s => s.aggregation_type === 'state');
    const width = 100 / Math.max(rows.length, 1);
    const pattern = StateEntities.unavailablePattern();
    chart.setOption({
      tooltip: {
        trigger: 'item',
        backgroundColor: surface,
        textStyle: {color: style.getPropertyValue('--ink-muted').trim(), fontFamily: style.getPropertyValue('--font-mono'), fontSize: scaledFont(12)},
        appendToBody: true,
      },
      series: rows.map((s, k) => ({
        type: 'pie',
        radius: rows.length > 1 ? ['36%', '60%'] : ['52%', '85%'],
        center: [`${width * k + width / 2}%`, '50%'],
        label: {show: false},
        labelLine: {show: false},
        itemStyle: {borderColor: surface, borderWidth: 2},
        tooltip: {
          formatter: p => `${escapeHtml(entityNames[s.entity_id] || s.friendly_name)}<br>${p.marker} <strong>${escapeHtml(p.name)}</strong><br>`
            + `${NumberFormat.fmtDuration(p.value)} (${fmtCompactNumber(p.percent, 1)} %)`,
        },
        data: stateRows(s, windowEnd).map(row => ({
          name: row.label, value: row.seconds, itemStyle: {color: StateEntities.fill(row.idx, pattern)},
        })),
      })),
    }, true);
  }

  function renderTileDonut(chart, series, entityNames, colorFor, aggregation, effectiveDecimals, style, surface, hiddenSet) {
    const data = series.map(s => {
      const values = (s.points || []).map(p => p.value).filter(Number.isFinite);
      let value = 0;
      if (values.length) {
        if (aggregation === 'average') value = values.reduce((sum, v) => sum + v, 0) / values.length;
        else if (aggregation === 'last') value = values[values.length - 1];
        else value = values.reduce((sum, v) => sum + v, 0);
      }
      return {
        name: entityNames[s.entity_id] || s.friendly_name,
        value: Math.max(0, value),
        itemStyle: {color: colorFor(s.entity_id)},
      };
    });
    // Serien-Umschalter der Legende (toggleTileLegendItem()) wirkt bei
    // type:'pie' auf einzelne DATENPUNKTE statt auf ganze Serien — ECharts
    // behandelt jeden data-Eintrag wie einen eigenen Legendeneintrag (per
    // name), legendToggleSelect trifft darüber trotzdem genau den richtigen
    // Slice. Ohne dieses (unsichtbare, show:false — wie im Zeitverlauf-Zweig
    // oben) legend-Objekt hätte die Aktion nichts zum Umschalten.
    const legendSelected = {};
    data.forEach(d => { legendSelected[d.name] = !hiddenSet || !hiddenSet.has(d.name); });
    chart.setOption({
      legend: {show: false, data: data.map(d => d.name), selected: legendSelected},
      tooltip: {
        trigger: 'item',
        backgroundColor: surface,
        textStyle: {color: style.getPropertyValue('--ink-muted').trim(), fontFamily: style.getPropertyValue('--font-mono'), fontSize: scaledFont(12)},
        formatter: p => {
          const s = series[p.dataIndex];
          const unit = s.unit ? ` ${escapeHtml(s.unit)}` : '';
          return `${p.marker} ${escapeHtml(p.name)}: <strong>${fmtCompactNumber(p.value, effectiveDecimals(s))}${unit}</strong> (${fmtCompactNumber(p.percent, 1)} %)`;
        },
        appendToBody: true,
      },
      series: [{
        type: 'pie',
        radius: ['52%', '85%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        label: {show: false},
        labelLine: {show: false},
        itemStyle: {borderColor: surface, borderWidth: 2},
        emphasis: {scaleSize: 6, itemStyle: {shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.25)'}},
        data,
      }],
    }, true);
  }

  // Alle Einstellungen eines Charts als reine Daten. ds ist ein DOMStringMap
  // (Kachel: el.dataset) oder ein gleich benanntes Objekt (Zeichenketten).
  function readSpec(ds) {
    // Volle Auswahl UND die ausgeblendeten getrennt: abgefragt und gezeichnet
    // werden nur die sichtbaren, die Farbe hängt aber an der Position in der
    // vollen Auswahl (colorIndexFor unten) — sonst wäre dieselbe Serie auf der
    // Chart-Seite und auf der Kachel unterschiedlich eingefärbt, sobald eine
    // Serie ausgeblendet ist. Gleiche Regel wie colorIndexFor() in
    // pages/chart_editor.js.
    const allEntityIds = JSON.parse(ds.entityIds || '[]');
    const hiddenEntityIds = JSON.parse(ds.hiddenEntityIds || '[]');
    const entityIds = allEntityIds.filter(id => !hiddenEntityIds.includes(id));
    const colorIndexFor = (entityId) => {
      const idx = allEntityIds.indexOf(entityId);
      return idx === -1 ? 0 : idx;
    };
    // Eigene Farbe je Serie (saved_charts.series_colors, "palette:N" oder
    // "#rrggbb"), sonst Palettenfarbe nach Position. Gleiche Regel wie
    // colorFor() in pages/chart_editor.js.
    let seriesColors = {};
    try { seriesColors = JSON.parse(ds.seriesColors || '{}') || {}; } catch (e) { seriesColors = {}; }
    const colorFor = (entityId) => {
      const own = seriesColors[entityId];
      if (typeof own === 'string') {
        if (own.startsWith('palette:') && PALETTE[+own.slice(8)]) return PALETTE[+own.slice(8)];
        if (/^#[0-9a-f]{6}$/i.test(own)) return own;
      }
      return PALETTE[colorIndexFor(entityId) % PALETTE.length];
    };
    const entityNames = JSON.parse(ds.entityNames || '{}');
    const range = ds.range || 'day';
    const continuous = ds.continuous === 'true';
    const resolutionPreset = ds.resolutionPreset || 'auto';
    // Siehe chart_editor.html (render(), dynamicYAxis-Konstante): bei
    // Auflösung t("Tag") (singleBucket in draw()) erzwungen aus, unabhängig
    // vom gespeicherten Chart-Zustand — eine nicht bei 0 startende Y-Achse
    // würde den Summen-Vergleich der wenigen Balken verzerren.
    const dynamicYAxis = ds.dynamicYAxis === 'true' && resolutionPreset !== 'full';
    const animation = ds.animation !== 'false';
    // Wie chart_editor.html: Zeitstrahl braucht immer echte Rohübergänge,
    // nie Bucket-Werte (siehe dortiger Kommentar bei setRange()/load() —
    // Bucket-Werte würden als fälschlich durchgehende AN-Intervalle statt
    // echter Übergänge gezeichnet).
    const chartType = ds.chartType || 'auto';
    const timeline = chartType === 'timeline';
    // "Darstellungsart" Donut (Optionen-Menü der Chart-Seite) — Kachel-
    // Parität zu chart_editor.js renderDonut(), siehe donut-Zweig in draw()
    // und renderTileDonut().
    const donut = chartType === 'donut';
    const donutAggregation = ds.donutAggregation || 'sum';
    // Nachkommastellen-Override (Optionen-Menü, "Darstellung") — bei "Auto"
    // behält jede Serie ihre eigene entities.decimals-Einstellung (s.decimals,
    // vom Server je Entität geliefert), sonst gilt dieser Wert für ALLE Serien
    // dieser Kachel einheitlich, genau wie in chart_editor.html (effectiveDecimals()).
    const decimalsOverride = ds.decimals || 'auto';
    const effectiveDecimals = s => decimalsOverride === 'auto' ? s.decimals : parseInt(decimalsOverride, 10);
    // "Werte anzeigen" (Optionen-Menü) — bislang nicht an die Dashboard-Kachel
    // durchgereicht, siehe showValues-Verwendung im echartsSeries-Aufbau in draw().
    const showValues = ds.showValues === 'true';
    // "Durchschnittslinie" (Optionen-Menü der Chart-Seite) — die Kachel
    // zeichnet sie mit, damit ein angeheftetes Chart nicht anders aussieht als
    // dasselbe Chart auf seiner eigenen Seite.
    const averageLine = ds.averageLine === 'true';
    // "Flach"/"Gleitend" (verschachtelt unter "Durchschnittslinie" im
    // Chart-Editor) — dieselbe Kachel-Parität wie averageLine selbst.
    const averageStyle = ds.averageStyle || 'flat';
    // "Fläche" (Optionen-Menü der Chart-Seite, chart_editor.js) — dieselbe
    // dezente Füllfläche wie auf der eigenen Chart-Seite, damit ein
    // angeheftetes Chart nicht anders aussieht als dasselbe Chart dort.
    const areaFill = ds.areaFill !== 'false';
    const showPoints = ds.showPoints === 'true';
    // "Gestapelt"/"Anteile (%)" (Optionen-Menü der Chart-Seite) — dieselbe
    // stacked-Kachel-Vorschau wie auf der eigenen Chart-Seite, siehe
    // stackedActive/normalizeActive in draw() (chart_editor.js-Parität).
    const stacked = ds.stacked === 'true';
    const normalize = ds.normalize === 'true';
    // "Ausrichtung" (Optionen-Menü, nur bei Auflösung "Voll") — siehe
    // horizontalActive in draw() (chart_editor.js-Parität).
    const horizontal = ds.horizontal === 'true';
    // Gezeichneter Zustand je Zustands-Entität der Heatmap (saved_charts.heatmap_states).
    let heatmapStates = {};
    try { heatmapStates = JSON.parse(ds.heatmapStates || '{}') || {}; } catch (e) { heatmapStates = {}; }
    const spec = {
      entityIds, entityNames, colorFor, range, continuous, resolutionPreset, dynamicYAxis, animation,
      chartType, timeline, donut, donutAggregation, effectiveDecimals, showValues, averageLine,
      averageStyle, areaFill, showPoints, stacked, normalize, horizontal, heatmapStates,
      periodAnchor: ds.periodAnchor || '',
      compareSettings: ds.compareSettings || '',
    };
    spec.compare = tileCompare(spec);
    return spec;
  }

  // Lädt die Reihen eines Charts. base: Präfix der App (Ingress), stichtag:
  // Stichtag der Zeitraum-Navigation oder null, widthPx: Breite der Zeichenfläche
  // (für die Spalten des Zeitstrahls in Jahr/Dekade). Wirft bei Netzwerkfehlern.
  async function fetchChartData(spec, {base = '', stichtag = null, widthPx = 0} = {}) {
    const {range, continuous, entityIds, chartType, timeline, compare} = spec;
    // Fester Zeitraum des Charts (saved_charts.period_anchor, JJJJ-MM-TT):
    // dieselbe Umrechnung in einen Versatz wie im Chart-Editor, damit Kachel
    // und Chart-Seite dieselbe Periode zeigen. Ohne Anker die laufende.
    let offset = 0;
    if (spec.periodAnchor) {
      const [y, m, d] = spec.periodAnchor.split('-').map(Number);
      offset = PeriodNavigation.offsetForRange(range, new Date(y, m - 1, d, 12).getTime());
    }
    const params = new URLSearchParams({
      entity_ids: entityIds.join(','), range, offset: String(offset), continuous: String(continuous),
      raw: String(timeline),
    });
    // Ein fester Zeitraum bleibt fest, der Stichtag gilt nur für die übrigen.
    if (!spec.periodAnchor && stichtag) params.set('at', stichtag);
    if (compare) {
      params.set('compare', 'true');
      params.set('compare_mode', compare.mode);
      if (compare.longterm) params.set('previous_years', String(compare.years));
    }
    // Heatmap: zusätzlich die Zellen (Wochentag x Stunde), wie im Chart-Editor.
    // Zu kurze Zeiträume fallen in viewTypeFor() auf den Standard zurück.
    const wantHeatmap = chartType === 'heatmap' && StateEntities.SERVER_SHARE_RANGES.includes(range);
    const heatmapParams = new URLSearchParams(params);
    heatmapParams.set('heatmap', 'true');
    heatmapParams.delete('compare');
    // Zeitstrahl in Jahr/Dekade: zusätzlich Spalten vom Server, so breit wie die Kachel,
    // wie im Chart-Editor. Sie ersetzen die Rohabschnitte, wenn deren Abfrage abbricht.
    const wantColumns = timeline && StateEntities.COLUMN_RANGES.includes(range);
    const columnsParams = new URLSearchParams(params);
    columnsParams.set('columns', 'true');
    columnsParams.delete('compare');
    columnsParams.set('px', String(Math.max(60, Math.round(widthPx - 10))));
    const [res, heatmapRes, columnsRes] = await Promise.all([
      fetch(`${base}/api/query-multi?${params}`),
      wantHeatmap ? fetch(`${base}/api/query-multi?${heatmapParams}`) : Promise.resolve(null),
      wantColumns ? fetch(`${base}/api/query-multi?${columnsParams}`) : Promise.resolve(null),
    ]);
    const columnsData = columnsRes && columnsRes.ok ? await columnsRes.json() : null;
    const data = res.ok ? await res.json() : (columnsData || {});
    const heatmapData = heatmapRes ? await heatmapRes.json() : null;
    if (heatmapData) {
      const cellsById = new Map((heatmapData.series || []).map(x => [x.entity_id, x.cells]));
      for (const entry of data.series || []) if (cellsById.get(entry.entity_id)) entry.cells = cellsById.get(entry.entity_id);
    }
    if (columnsData && data !== columnsData) {
      const colsById = new Map((columnsData.series || []).filter(x => x.columns).map(x => [x.entity_id, x]));
      for (const entry of data.series || []) {
        const cols = colsById.get(entry.entity_id);
        if (cols) { entry.columns = cols.columns; entry.dt = cols.dt; }
      }
    }
    return data;
  }

  // Zustände lassen sich nur unter sich darstellen (wie im Chart-Editor):
  // steht etwas anderes im Chart, fallen sie heraus.
  function prepareSeries(data) {
    const loaded = data.series || [];
    const foreign = loaded.some(s => s.aggregation_type && s.aggregation_type !== 'state');
    return foreign ? loaded.filter(s => s.aggregation_type !== 'state') : loaded;
  }

  const hasData = series => series.some(s => (s.points && s.points.length) || (s.columns && s.columns.length));

  // Nur Zustände und keine Ansicht gewählt: je Zeitraum der Standard, wie im
  // Chart-Editor (Zeitstrahl bis zur Woche, danach Anteile).
  function viewTypeFor(spec, series) {
    const {chartType, range} = spec;
    const heatmapTooShort = chartType === 'heatmap' && !StateEntities.SERVER_SHARE_RANGES.includes(range);
    return (chartType === 'auto' || heatmapTooShort) && series.every(s => s.aggregation_type === 'state')
      ? StateEntities.defaultMode(range) : chartType;
  }

  // Zeichnet das Chart. ctx: spec (readSpec), data (fetchChartData), series
  // (prepareSeries), viewType (viewTypeFor), multiYear (tileMultiYear oder
  // null), hiddenSet (per Legende ausgeblendete Serien oder undefined) und
  // style (computed style, aus dem die Farben gelesen werden — Canvas kennt
  // keine CSS-Variablen).
  function draw(chart, ctx) {
    const {spec, data, series, viewType, multiYear, hiddenSet, style} = ctx;
    const {
      entityNames, colorFor, range, resolutionPreset, dynamicYAxis, animation, timeline, donut,
      donutAggregation, effectiveDecimals, showValues, averageLine, averageStyle, areaFill,
      showPoints, stacked, normalize, horizontal, heatmapStates, compare,
    } = spec;
    const borderColor = style.getPropertyValue('--border').trim();
    const inkFaint = style.getPropertyValue('--ink-faint').trim();
    const inkMuted = style.getPropertyValue('--ink-muted').trim();
    const surface = style.getPropertyValue('--surface').trim();

    // Zeitstrahl statt Linie/Balken — eigener, kompakter Renderpfad (analog
    // renderTimelineMulti() in chart_editor.html), springt hier komplett aus
    // der Linie-/Balken-Aufbereitung unten heraus, die bei AN/AUS-Intervallen
    // ohnehin keinen Sinn ergäbe.
    if (multiYear) {
      renderTileMultiYear(chart, multiYear, series[0], {
        effectiveDecimals, animation, style, borderColor, inkFaint, inkMuted, surface,
        hiddenSet,
      });
      return;
    }
    if (compare?.yearsCompare) {
      renderTileYearsCompare(chart, series, compare, data, {
        entityNames, colorFor, effectiveDecimals, animation, style, borderColor, inkFaint, inkMuted, surface,
        hiddenSet,
      });
      return;
    }
    if (viewType === 'heatmap' && series.some(s => s.aggregation_type === 'state')) {
      renderTileStateHeatmap(chart, series, entityNames, animation, heatmapStates);
      return;
    }
    if (['shares', 'changes'].includes(viewType) && series.some(s => s.aggregation_type === 'state')) {
      renderTileStateBars(chart, series, entityNames, data, range, viewType, animation);
      return;
    }
    if (timeline || viewType === 'timeline') {
      renderTileTimeline(chart, series, entityNames, data, range, animation, style, borderColor, inkFaint, surface, colorFor);
      return;
    }
    if (donut && series.some(s => s.aggregation_type === 'state')) {
      renderTileStateDonuts(chart, series, entityNames, data.window_end, style, surface);
      return;
    }
    if (donut) {
      renderTileDonut(chart, series, entityNames, colorFor, donutAggregation, effectiveDecimals, style, surface, hiddenSet);
      return;
    }

    // Eine Y-Achse je unterschiedlicher Einheit (genau wie auf der vollen
    // Chart-Seite, chart_editor.html) — ohne das teilen sich z. B. Watt- und
    // kWh-Werte dieselbe Achse, wodurch die kWh-Balken bei einer viel
    // größeren Watt-Spanne rechnerisch bei ~0 verschwinden, statt sichtbar zu
    // sein. Kompakt gehalten: kein Achsenname, nur die Zahl.
    // Schalter-Entitäten im Anzeigemodus "Zeit" (Dauer statt Rohsekunden)
    // bekommen wie in chart_editor.html einen eigenen synthetischen Achsen-
    // Schlüssel statt ihrer echten (meist leeren) unit — sonst teilten sie
    // sich fälschlich eine Achse mit unitlosen Standard-Entitäten und
    // erschienen dort in rohen Sekunden statt als Dauer (Achse UND Tooltip
    // kannten den Anzeigemodus bisher gar nicht, nur die HTML-Legende oben).
    const isDurationSeries = s => s.aggregation_type === 'switch' && s.display_mode === 'time';
    const axisKey = s => isDurationSeries(s) ? ' duration' : s.unit;
    const units = [...new Set(series.map(axisKey))];
    // Auflösung "Voll" (Tag/Woche/Monat/Jahr) fasst den kompletten Zeitraum
    // zu genau EINEM Wert je Entität zusammen — ein Ranking-Vergleich, kein
    // Zeitverlauf. Jede Entität bekommt dafür eine eigene Kategorie auf der
    // Achse (ihr Anzeigename), siehe chart_editor.js (gleicher Name/
    // Kommentar dort für die ausführliche Begründung).
    const singleBucket = resolutionPreset === 'full';
    const horizontalActive = singleBucket && horizontal;
    const entityCategories = series.map(s => entityNames[s.entity_id] || s.friendly_name);
    // Wie chart_editor.js: "Gestapelt" nur ab zwei Balken-Serien UND
    // außerhalb von Auflösung "Voll" (dort hat jede Entität schon ihre
    // eigene Kategorie — eine gestapelte Kombination aller Entitäten in
    // EINER Kategorie wäre ein Widerspruch dazu), je Achse ein eigener
    // Stapel-Schlüssel statt eines globalen "total" (eine Kachel kann
    // mehrere Einheiten kombinieren, z. B. kWh und Dauer), und 100%-
    // Normierung nur auf Achsen, auf denen AUSSCHLIESSLICH Balken liegen —
    // eine mitgezeichnete Linie derselben Einheit stünde sonst auf einer
    // 0–100%-Skala, die für die gestapelten Balken gemeint ist.
    const stackedActive = stacked && !singleBucket && series.filter(s => s.chart_type === 'bar').length >= 2;
    const normalizeActive = stackedActive && normalize;
    const barOnlyAxis = new Set(
      units.filter(u => series.every(s => axisKey(s) !== u || s.chart_type === 'bar'))
    );
    // Strengste (kleinste) Nachkommastellen-Einstellung aller Entitäten einer
    // gemeinsamen Achse — dieselbe Regel wie in chart_editor.html.
    const unitDecimals = new Map();
    series.forEach(s => {
      const d = effectiveDecimals(s);
      if (d == null) return;
      const current = unitDecimals.get(axisKey(s));
      if (current == null || d < current) unitDecimals.set(axisKey(s), d);
    });
    const yAxis = units.map((u, i) => {
      const decimals = unitDecimals.get(u);
      const isDuration = u === ' duration';
      // Balken zeichnen immer von der Null-Basislinie zum Wert — liegt eine
      // auto-skalierte Achse (scale:true, min/max undefined) nicht bei 0,
      // ragt der Balken optisch über den unteren Achsenrand hinaus statt
      // sauber auf der x-Achse zu stehen. "Dynamische Y-Achse" gilt deshalb
      // nur für Achsen, auf denen ausschließlich Linien-Serien liegen —
      // je Achse geprüft, da eine Kachel mehrere Einheiten/Achsen mischen kann.
      const axisHasBar = series.some(s => axisKey(s) === u && s.chart_type === 'bar');
      const axisDynamic = dynamicYAxis && !axisHasBar;
      // Prozent-Achse (100%-Normierung) — immer fest 0–100, unabhängig von
      // "Dynamische Y-Achse", siehe chart_editor.js (gleiche Begründung).
      const isPercentAxis = normalizeActive && barOnlyAxis.has(u);
      return {
        type: 'value',
        position: i % 2 === 0 ? 'left' : 'right',
        offset: Math.floor(i / 2) * 46,
        min: isPercentAxis ? 0 : (axisDynamic ? undefined : value => Math.min(0, value.min)),
        max: isPercentAxis ? 100 : (axisDynamic ? undefined : value => Math.max(0, value.max)),
        // Siehe chart_editor.html: ohne scale:true erzwingt ECharts bei einer
        // value-Achse per Default immer die Einbindung der Null, auch bei
        // undefined min/max — "Dynamische Y-Achse" hätte sonst keine
        // sichtbare Wirkung.
        scale: isPercentAxis ? false : axisDynamic,
        axisLabel: {
          fontSize: scaledFont(10), color: inkFaint,
          formatter: v => isPercentAxis ? `${fmtCompactNumber(v, 0)} %` : (isDuration ? NumberFormat.fmtDuration(v) : fmtCompactNumber(v, decimals)),
        },
        axisLine: {show: false},
        axisTick: {show: false},
        splitLine: {lineStyle: {color: borderColor, type: 'dashed'}},
      };
    });
    // "Ausrichtung: Horizontal" tauscht Kategorie- und Werte-Achse — dasselbe
    // Position-Remapping wie chart_editor.js (siehe dortiger Kommentar).
    const xAxisForHorizontal = horizontalActive
      ? yAxis.map((axis, i) => ({...axis, position: i % 2 === 0 ? 'bottom' : 'top'}))
      : null;
    // Kategorie-Achse für singleBucket — Entitätsnamen statt Zeit-Ticks.
    const categoryAxisObj = singleBucket ? {
      type: 'category',
      data: entityCategories,
      axisTick: {show: false},
      axisLine: {show: false, onZero: false},
      axisLabel: {
        fontSize: scaledFont(10), color: inkFaint,
        width: horizontalActive ? 120 : 60,
        overflow: 'truncate',
        rotate: horizontalActive ? 0 : 28,
      },
    } : null;

    // Erste Serie mit genug angezeigten (resamplePoints()-) Punkten bestimmt
    // die Tooltip-Zeitstempel-Form (fmtTooltipTimestamp) — dieselbe Logik wie
    // chart_editor.html. Aus den resampelten, nicht den rohen Server-Punkten:
    // bei manuell gesetzter Auflösung (Kachel-Auflösung ungleich "auto")
    // resamplePoints() clientseitig gröber, die rohen Punkte wären dann
    // feiner als das, was im Tooltip tatsächlich zu sehen ist. Erst innerhalb
    // der Schleife unten gesetzt (dort liegen die resampelten displayPoints
    // vor), hier nur deklariert.
    let tooltipBucketSeconds = null;

    // Erster Durchgang: je Serie die anzuzeigenden Punkte berechnen (wie
    // bisher) — VOR dem eigentlichen Kachel-Aufbau, damit die 100%-
    // Normierung unten die Werte ALLER Serien einer Achse zum selben Bucket
    // kennt, bevor die erste Serie fertig gebaut wird.
    const prepared = series.map((s, i) => {
      // Die Punkte, über die der Durchschnitt geht: das GEZEICHNETE, aber
      // ohne den Halte-Punkt, den der Linien-Zweig unten bis window_end
      // anhängt — der ist eine Wiederholung des letzten Werts und würde
      // ihn doppelt zählen.
      if (singleBucket) {
        // resamplePoints() kennt nur "medium"/"coarse" (RESOLUTION_SECONDS),
        // für "full" gibt sie unverändert alle Rohpunkte zurück — ohne diesen
        // eigenen Zweig würde jeder einzelne Bucket-Punkt als eigener
        // Tooltip-Eintrag auf der eigenen Kategorie (x=i) landen, statt zu
        // einem einzigen Balkenwert für den ganzen Zeitraum zusammengefasst
        // zu werden (sichtbar als lange Dopplung im Tooltip). Dieselbe Summe-
        // vs.-Durchschnitt-Regel wie in den Legenden-Kennzahlen oben.
        const rawValues = (s.points || []).map(p => p.value).filter(Number.isFinite);
        if (!rawValues.length) return {lineData: [], averageValues: [], rawPoints: []};
        const isSumType = s.aggregation_type === 'counter' || s.aggregation_type === 'switch';
        const aggregate = isSumType
          ? rawValues.reduce((sum, v) => sum + v, 0)
          : rawValues.reduce((sum, v) => sum + v, 0) / rawValues.length;
        return {
          // x-Position ist die EIGENE Kategorie dieser Entität (ihre Position
          // in series, s. entityCategories), nicht mehr 0 für alle — seit
          // jede Entität ihre eigene Kategorie bekommt (s. o.).
          lineData: [[i, aggregate, s.unit, effectiveDecimals(s), isDurationSeries(s)]],
          averageValues: [aggregate],
          rawPoints: [{ts: data.window_start, value: aggregate}],
        };
      }
      const displayPoints = resamplePoints(
        s.points, range, resolutionPreset, s.aggregation_type, data.window_start
      );
      if (tooltipBucketSeconds == null) {
        tooltipBucketSeconds = detectResolutionSeconds(displayPoints);
      }
      const lineData = displayPoints.map(p => [p.ts * 1000, p.value, s.unit, effectiveDecimals(s), isDurationSeries(s)]);
      const averageValues = displayPoints.map(p => p.value);
      if (s.chart_type === 'line' && lineData.length && data.window_end != null
          && lineData[lineData.length - 1][0] < data.window_end * 1000) {
        const last = lineData[lineData.length - 1];
        lineData.push([data.window_end * 1000, last[1], last[2], last[3], last[4]]);
      }
      // rawPoints (ohne Halte-Punkt) für den gleitenden Durchschnitt — dieselbe
      // Begründung wie bei averageValues: der Halte-Punkt wiederholt nur den
      // letzten Wert und würde das Fenster am Rand verfälschen.
      return {lineData, averageValues, rawPoints: displayPoints};
    });
    // x (ms-Zeitstempel bzw. 0 bei singleBucket) -> Summe je Achse, nur für
    // tatsächlich normierte reine Balken-Achsen (barOnlyAxis, s. o.).
    const axisTotals = new Map();
    if (normalizeActive) {
      series.forEach((s, i) => {
        const u = axisKey(s);
        if (!barOnlyAxis.has(u)) return;
        if (!axisTotals.has(u)) axisTotals.set(u, new Map());
        const totals = axisTotals.get(u);
        prepared[i].lineData.forEach(p => totals.set(p[0], (totals.get(p[0]) || 0) + p[1]));
      });
    }
    // Letzter Balken-Index je Achse — nur der bekommt beim Stapeln abgerundete
    // obere Ecken (das oberste, sichtbare Ende des Stapels), statt wie im
    // gruppierten Fall JEDES Segment einzeln abzurunden.
    const lastBarIndexForAxis = new Map();
    series.forEach((s, i) => { if (s.chart_type === 'bar') lastBarIndexForAxis.set(axisKey(s), i); });

    // Gesammelt statt direkt in echartsSeries gepusht — series.map() liefert
    // genau ein Element je Durchlauf, die Trendlinie ist aber eine
    // ZUSÄTZLICHE, eigenständige Serie (siehe showRollingAverage unten).
    const rollingSeries = [];
    // Linien- und Balken-Serien, deren Tooltip-Zeile auch ohne eigenen Punkt am
    // Cursor erscheint (tooltip-hold.js, gleiche Regel wie chart_editor.js).
    const holdSeries = [];
    const echartsSeries = series.map((s, i) => {
      const color = colorFor(s.entity_id);
      const displayName = entityNames[s.entity_id] || s.friendly_name;
      const isStackedBar = s.chart_type === 'bar' && stackedActive;
      // 100%-Normierung nur auf reinen Balken-Achsen und nur für Balken-
      // Serien — eine überlagerte Linie derselben Einheit bleibt unverändert
      // in Absolutwerten (barOnlyAxis enthält ihre Achse dann nicht).
      const axisNormalized = normalizeActive && s.chart_type === 'bar' && barOnlyAxis.has(axisKey(s));
      let lineData = prepared[i].lineData;
      if (axisNormalized) {
        const totals = axisTotals.get(axisKey(s));
        // Felder 6/7 (Originaleinheit/-Nachkommastellen) stehen schon an
        // Position 2/3 des Ausgangs-Tupels — direkt übernommen statt erneut
        // nachgeschlagen. Feld 5: der Original-Absolutwert, nur für den
        // Tooltip (siehe formatter unten) — sonst verliert der Tooltip genau
        // die Zahl, die die Normierung aus dem Balken selbst entfernt.
        lineData = lineData.map(p => {
          const total = totals.get(p[0]) || 0;
          const pct = total ? (p[1] / total) * 100 : 0;
          return [p[0], pct, '%', 0, false, p[1], p[2], p[3]];
        });
      }
      // Gleitender Durchschnitt nur für Linien-Serien — dieselbe Begründung
      // wie chart_editor.js (eine Balken-Bucket-SUMME gleitend zu mitteln
      // ergäbe keine klar lesbare Aussage).
      const showRollingAverage = averageLine && !isStackedBar && averageStyle === 'rolling'
        && s.chart_type === 'line' && prepared[i].rawPoints.length >= 3;
      const cfg = {
        // Angepasster Anzeigename (chart_editor.html, "Angezeigte Namen") hat
        // Vorrang vor dem Entität-eigenen friendly_name — dieselbe Regel wie
        // beim Rendern der vollen Chart-Seite (dort this.entityNames[entity_id]).
        name: displayName,
        type: s.chart_type,
        // Horizontal tauschen Kategorie- und Werte-Achse die Plätze (s.
        // xAxisForHorizontal oben) — dieselbe Umkehr wie chart_editor.js.
        xAxisIndex: horizontalActive ? units.indexOf(axisKey(s)) : undefined,
        yAxisIndex: horizontalActive ? 0 : units.indexOf(axisKey(s)),
        data: lineData,
        // ECharts liest data-Tupel bei Balken/Linien sonst POSITIONAL als
        // [x, y] — unabhängig davon, welche Achse gerade Kategorie- bzw.
        // Werte-Achse ist. lineData[0] ist immer der Kategorie-Index, [1] der
        // Wert; horizontal tauschen xAxis/yAxis ihre Rollen (s. o.), also muss
        // ECharts das explizit gesagt werden — sonst interpretiert es den
        // Kategorie-Index als x-Wert und den Messwert als Kategorie-Index
        // (Balken verschwinden, Werte-Achse skaliert auf ~Kategorien-Anzahl).
        encode: horizontalActive ? {x: 1, y: 0} : undefined,
        stack: isStackedBar ? 'bar-' + axisKey(s) : undefined,
        // Bei aktiver Trendlinie tritt die rohe Kurve zurück, bleibt aber
        // sichtbar — dieselbe Ergänzung-statt-Ersatz-Logik wie im Editor.
        lineStyle: {width: 2, color, opacity: showRollingAverage ? 0.45 : 1},
        itemStyle: {color},
        // "Werte anzeigen" (Optionen-Menü) — Zahl direkt über jedem Balken/
        // Punkt, dieselbe Konvention wie entity_detail.html (ohne Einheit,
        // die steht schon an der Y-Achse). Gestapelt liegt das Label
        // INNERHALB des Segments (weiß) statt darüber — siehe chart_editor.js.
        label: {
          show: showValues,
          position: isStackedBar ? 'inside' : (horizontalActive ? 'right' : 'top'),
          fontSize: scaledFont(10),
          color: isStackedBar ? '#fff' : inkMuted,
          formatter: params => params.value[4]
            ? NumberFormat.fmtDuration(params.value[1])
            : fmtCompactNumber(params.value[1], params.value[3]),
        },
        // Gilt jetzt auch für singleBucket: seit jede Entität ihre eigene
        // Kategorie hat, ist das der Normalfall eines Kategorie-Achsen-
        // Balkens, kein Sonderfall mehr (siehe chart_editor.js).
        barMaxWidth: 28,
        // Ein Balken auf einer Zeit-Achse (kein boundaryGap, s. u.) sitzt mit
        // seiner Mitte GENAU auf dem Bucket-Zeitstempel — beim ersten/letzten
        // Bucket liegt die Hälfte der Balkenbreite dadurch zwangsläufig knapp
        // jenseits von min/max und würde ohne dies hart am Kachelrand
        // abgeschnitten wirken. Bei singleBucket (echte Kategorie-Achse mit
        // eigener Bandbreite je Kategorie) entfällt dieses Problem.
        clip: singleBucket ? undefined : s.chart_type !== 'bar',
      };
      if (s.chart_type === 'line') {
        cfg.smooth = true;
        if (!showPoints) cfg.symbol = 'none';
        // Dezente Füllfläche unter der Linie — macht eine einzelne Kurve auf
        // den ersten Blick lesbarer, stört bei mehreren überlagerten Serien
        // dank der niedrigen Deckkraft nicht. Abschaltbar (Optionen-Menü,
        // "Fläche"), Default an — siehe chart_editor.js.
        if (areaFill) cfg.areaStyle = {color, opacity: 0.08};
      } else if (!stackedActive) {
        cfg.itemStyle.borderRadius = [3, 3, 0, 0];
      } else if (lastBarIndexForAxis.get(axisKey(s)) === i) {
        // Nur das oberste Segment jedes Stapels abrunden — jedes einzelne
        // Segment abzurunden sähe wie mehrere getrennte Balken aus, nicht
        // wie ein durchgehender Stapel.
        cfg.itemStyle.borderRadius = [3, 3, 0, 0];
      }
      // Durchschnittslinie je Serie, in deren Farbe und auf deren y-Achse.
      // Ohne Einheit im Text: die Kachel beschriftet auch ihre Werte
      // (showValues) nur mit der Zahl, und der Platz ist hier knapper als auf
      // der Chart-Seite. Entschieden: im gestapelten Modus weggelassen —
      // dieselbe Begründung wie in chart_editor.js (eine Serie beginnt darin
      // nicht mehr bei 0).
      const durchschnitt = averageLine && !isStackedBar && averageStyle === 'flat'
        ? averageOf(prepared[i].averageValues) : null;
      if (durchschnitt !== null) {
        cfg.markLine = {
          silent: true,
          symbol: 'none',
          lineStyle: {color, type: 'dashed', width: 1},
          label: {
            position: 'insideEndTop',
            fontSize: scaledFont(10),
            color: inkMuted,
            formatter: () => `Ø ${fmtCompactNumber(durchschnitt, effectiveDecimals(s))}`,
          },
          data: [horizontalActive ? {xAxis: durchschnitt} : {yAxis: durchschnitt}],
        };
      }
      if (showRollingAverage) {
        const windowPoints = movingAverageWindow(prepared[i].rawPoints.length);
        const rollingData = movingAverage(prepared[i].rawPoints, windowPoints)
          .filter(p => p.value !== null)
          .map(p => [p.ts * 1000, p.value]);
        // Eigene, zusätzliche Serie statt eines markLine/Umbaus der
        // Hauptserie — dieselbe Technik wie chart_editor.js. Nicht über die
        // Legende einzeln umschaltbar, sie gehört sichtbar zur Hauptserie.
        rollingSeries.push({
          name: `${displayName} (Ø gleitend)`,
          type: 'line',
          yAxisIndex: units.indexOf(axisKey(s)),
          data: rollingData,
          smooth: true,
          symbol: 'none',
          lineStyle: {width: 2.5, color},
          z: 3,
        });
      }
      if (!singleBucket && !horizontalActive) {
        holdSeries.push({seriesIndex: i, name: displayName, color, data: lineData, bucket: s.chart_type === 'bar'});
      }
      return cfg;
    });
    echartsSeries.push(...rollingSeries);
    // Vorjahr/Vorperiode als blassere, gestrichelte Nebenserie je Entität —
    // dieselbe Technik wie render() in chart_editor.js: um die exakte
    // Fensterdifferenz verschoben, nicht über den Array-Index zugeordnet.
    if (compare && !singleBucket) {
      series.forEach(s => {
        if (!s.compare_points || !s.compare_points.length) return;
        const color = colorFor(s.entity_id);
        const displayName = entityNames[s.entity_id] || s.friendly_name;
        const shiftMs = (s.compare_window_start != null && data.window_start != null)
          ? (data.window_start - s.compare_window_start) * 1000
          : 0;
        const comparePoints = resamplePoints(
          s.compare_points, range, resolutionPreset, s.aggregation_type, s.compare_window_start
        );
        const compareData = comparePoints.map(p => [p.ts * 1000 + shiftMs, p.value, s.unit, effectiveDecimals(s), isDurationSeries(s)]);
        if (s.chart_type === 'line' && compareData.length && data.window_end != null
            && compareData[compareData.length - 1][0] < data.window_end * 1000) {
          const last = compareData[compareData.length - 1];
          compareData.push([data.window_end * 1000, last[1], last[2], last[3], last[4]]);
        }
        const cmp = {
          name: `${displayName} (${compare.mode === 'year' ? t('Vorjahr') : t('Vorperiode')})`,
          type: s.chart_type,
          yAxisIndex: units.indexOf(axisKey(s)),
          data: compareData,
          lineStyle: {width: 1.5, color: withOpacity(color, 0.5), type: 'dashed'},
          itemStyle: {color: withOpacity(color, 0.5)},
          barMaxWidth: 28,
          clip: s.chart_type !== 'bar',
        };
        if (s.chart_type === 'line') {
          cmp.smooth = true;
          if (!showPoints) cmp.symbol = 'none';
          if (areaFill) cmp.areaStyle = {color, opacity: 0.05};
        } else {
          cmp.itemStyle.borderRadius = [3, 3, 0, 0];
        }
        echartsSeries.push(cmp);
      });
    }
    padStackedSeries(echartsSeries);

    // ECharts' eigene Legende bleibt unsichtbar (show:false, wie in
    // chart_editor.html) — die sichtbare Legende ist das eigene HTML-Element
    // (renderLegend()), legend.selected/data existieren hier nur, damit
    // legendToggleSelect (setupLegendToggles()) überhaupt etwas zum
    // Umschalten hat.
    const legendSelected = {};
    echartsSeries.forEach(s => { legendSelected[s.name] = !hiddenSet || !hiddenSet.has(s.name); });

    chart.setOption({
      animation,
      textStyle: {fontFamily: style.getPropertyValue('--font-mono')},
      color: PALETTE,
      // "Werte anzeigen": Die Zahl steht über (horizontal: rechts neben) dem
      // Balken, und die Y-Achse endet exakt beim Maximalwert. Ohne Rand würde
      // das Label des höchsten Balkens am Kachelrand abgeschnitten.
      grid: {
        left: 6,
        right: showValues && horizontalActive ? 36 : 6,
        top: showValues && !horizontalActive && !stackedActive ? 10 + scaledFont(10) + 6 : 10,
        bottom: 20,
        containLabel: true,
      },
      xAxis: singleBucket ? (horizontalActive ? xAxisForHorizontal : categoryAxisObj) : {
        type: 'time',
        min: axisMinForBars(echartsSeries, data.window_start != null ? data.window_start * 1000 : null),
        // period_end statt window_end: eine laufende Periode (z. B. Woche)
        // zeigt so bis zur vollen Kalendergrenze (Sonntag), auch für die noch
        // datenlose Zukunft — window_end (an "jetzt" gedeckelt) bleibt nur für
        // den Linien-Haltepunkt oben (lineData.push(...)) maßgeblich. Eine
        // Sekunde zurück, da period_end (wie window_end) EXKLUSIV ist — sonst
        // reicht die Achse sichtbar bis zum Beginn der nächsten Periode (ein
        // Achsen-Tick "01.09." für einen Monat, der am 31.08. endet).
        max: (data.period_end ?? data.window_end) != null ? (data.period_end ?? data.window_end) * 1000 - 1000 : undefined,
        boundaryGap: [0, 0],
        // Woche/Monat bucketen tagesweise (siehe fmtAxis()) — mit fest
        // erzwungenem Tages-Interval statt ECharts' automatischer "nice
        // tick"-Berechnung, die trotz explizitem max (s. o.) gelegentlich
        // einen zusätzlichen Tick (Gitternetz, nicht nur Label) jenseits der
        // Periodengrenze erzeugt. Nicht für Jahr/Dekade erzwungen: Monate/
        // Jahre sind unterschiedlich lang, ein fester Millisekunden-Interval
        // würde dort falsch ausgerichtete Ticks erzeugen.
        interval: ['week', 'month'].includes(range) ? 24 * 60 * 60 * 1000 : undefined,
        axisLabel: {
          // ECharts' eigene "nice tick"-Berechnung polstert eine Zeit-Achse
          // intern minimal über min/max hinaus (auch mit explizit gesetztem
          // max) — ohne diese Sperre erschiene trotz max oben vereinzelt noch
          // ein Tick auf der falschen Seite der Periodengrenze (z. B. "01.09."
          // für einen Monat, der am 31.08. endet). rawPeriodEndMs ist die
          // EXKLUSIVE Grenze (Beginn der Folgeperiode) — ab dort wird die
          // Beschriftung unterdrückt statt einfach nur die Achse zu kürzen.
          formatter: v => {
            const rawPeriodEndMs = (data.period_end ?? data.window_end) != null ? (data.period_end ?? data.window_end) * 1000 : null;
            if (rawPeriodEndMs != null && v >= rawPeriodEndMs) return '';
            return fmtAxis(range, v / 1000);
          },
          fontSize: scaledFont(10), color: inkFaint, hideOverlap: true,
        },
        axisLine: {lineStyle: {color: borderColor}},
        axisTick: {show: false},
        splitLine: {show: false},
      },
      yAxis: horizontalActive ? {...categoryAxisObj, inverse: true} : yAxis,
      tooltip: {
        trigger: 'axis',
        backgroundColor: surface,
        borderColor,
        textStyle: {color: inkMuted, fontFamily: style.getPropertyValue('--font-mono'), fontSize: scaledFont(12)},
        formatter: (allParams) => {
          // Auffüll-Punkte gestapelter Serien (padStackedSeries) haben keinen Wert.
          // Danach jede sichtbare Linien- und Balken-Serie mit ihrem letzten
          // bekannten Wert (tooltip-hold.js), auch ohne eigenen Punkt am Cursor.
          const legendState = chart.getOption().legend?.[0]?.selected || {};
          const params = TooltipHold.complete(
            allParams.filter(p => p.data[1] != null),
            holdSeries,
            name => legendState[name] !== false
          );
          if (!params.length) return '';
          // Bei singleBucket ist axisValue jetzt der Entitätsname (eigene
          // Kategorie je Entität, s. o.), keine Zeitangabe mehr — die
          // Kopfzeile zeigt stattdessen weiterhin den Periodenbeginn direkt
          // aus window_start, wie vor der Kategorie-je-Entität-Umstellung.
          const header = singleBucket
            ? (data.window_start != null ? new Date(data.window_start * 1000).toLocaleDateString(LOCALE, window.ServerTime.withZone({day: '2-digit', month: '2-digit', year: 'numeric'})) : '')
            : fmtTooltipTimestamp(params[0].axisValue, tooltipBucketSeconds);
          const rows = params.map(p => {
            const unit = p.data[2] || '';
            const decimals = p.data[3];
            const value = p.data[4]
              ? NumberFormat.fmtDuration(p.data[1])
              : `${fmtCompactNumber(p.data[1], decimals)}${unit ? ' ' + escapeHtml(unit) : ''}`;
            // 100%-Normierung: zeigt IMMER beides — Anteil und Original-
            // Absolutwert in Klammern (Felder 5–7, siehe axisNormalized oben)
            // — sonst verliert der Tooltip genau die Zahl, die die
            // Normierung aus dem Balken selbst entfernt.
            const absValue = p.data[5];
            const extra = absValue != null
              ? ` <span style="color:${inkFaint};">(${fmtCompactNumber(absValue, p.data[7])}${p.data[6] ? ' ' + escapeHtml(p.data[6]) : ''})</span>`
              : '';
            return `<div style="display:flex;justify-content:space-between;gap:14px;">`
                 + `<span>${p.marker}${escapeHtml(p.seriesName)}</span>`
                 + `<span style="margin-left:8px;text-align:right;"><strong>${value}${extra}</strong>`
                 + `${TooltipHold.note(p, inkFaint, ms => fmtTooltipTimestamp(ms, tooltipBucketSeconds))}</span></div>`;
          }).join('');
          return header ? `<div style="margin-bottom:4px;color:${inkFaint};">${header}</div>${rows}` : rows;
        },
        // Kachel hat overflow:hidden (verhindert, dass z. B. die Legende das
        // Kachel-Layout sprengt) — ohne appendToBody würde der Tooltip am
        // Kachelrand abgeschnitten statt sichtbar über die Kachel
        // hinauszuragen (siehe dieselbe Begründung in chart_editor.html/
        // entity_detail.html).
        appendToBody: true,
      },
      legend: {show: false, data: echartsSeries.map(s => s.name), selected: legendSelected},
      series: echartsSeries,
      // notMerge: ohne dies mergt ECharts neue Optionen standardmäßig nur in
      // den bestehenden State statt ihn zu ersetzen — bei jeder erneuten
      // renderTile()-Ausführung derselben Kachel (Resize, Größenwechsel,
      // Legenden-Umschalter) könnten so Reste vorheriger Aufrufe bestehen
      // bleiben. chart_editor.html nutzt aus demselben Grund ebenfalls
      // setOption(..., true).
    }, true);
  }

  window.ChartTileRender = {
    PALETTE,
    LOCALE,
    scaledFont,
    withOpacity,
    fmtCompactNumber,
    tileCompare,
    tileMultiYear,
    stateRows,
    switchOnDuration,
    readSpec,
    fetchChartData,
    prepareSeries,
    hasData,
    viewTypeFor,
    draw,
  };
})();
