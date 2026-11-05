// Diagramme der Dashboards Energie und Wetter als ECharts-Optionen, ohne Alpine und ohne Seitenzustand (Roadmap 1.48).
// Aus energie-langzeit.js und wetter.js herausgelöst: dieselben Optionen zeichnet das Dashboard und die Lovelace-Karte.
// Die Funktionen liefern nur das Option-Objekt; Instanz, Größe und Farben stellen Seite bzw. Karte. Braucht t(), escapeHtml
// und element-table-render.js (Monatsnamen, Statistik, Formate) als Globals.
(() => {
  const {monthName, monthStats, isPartialStart, energy} = window.ElementTableRender;
  const LOCALE = window.ZA_FORMAT;

  const num = (value, decimals) => NumberFormat.fmt(value, decimals);

  function axisStyle(colors, font) {
    return {
      axisLine: {lineStyle: {color: colors.grid}}, axisTick: {show: false},
      axisLabel: {color: colors.text, fontSize: font(11)},
      splitLine: {lineStyle: {color: colors.grid}},
    };
  }

  // Auf schmalen Flächen bricht die Legende in zwei Zeilen um und braucht mehr Platz über dem Diagramm.
  const gridFor = (narrow) => ({left: 8, right: 16, top: narrow ? 74 : 34, bottom: 8, containLabel: true});

  function legendBox(colors, data, font) {
    return {data, top: 0, textStyle: {color: colors.text, fontSize: font(12)}, itemWidth: 18, itemHeight: 8};
  }

  function tooltipBox(colors, font, formatter) {
    return {
      trigger: 'axis', confine: true, formatter,
      backgroundColor: colors.surface, borderColor: colors.grid,
      textStyle: {color: colors.ink, fontSize: font(12)},
    };
  }

  const MONTH_LENGTHS_LEAP = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const MONTH_STARTS_LEAP = MONTH_LENGTHS_LEAP.map((_len, index) => MONTH_LENGTHS_LEAP.slice(0, index).reduce((a, b) => a + b, 0));
  function leapSlotDate(slot) {
    let month = 11;
    while (MONTH_STARTS_LEAP[month] > slot) month--;
    return {month: month + 1, day: slot - MONTH_STARTS_LEAP[month] + 1};
  }

  // Kalendertag einer Spalte als UTC-Datum (Spalte 59 ist der 29.02. eines Schaltjahres).
  function matrixDate(year, slot) {
    const leapDay = new Date(Date.UTC(2024, 0, 1 + slot));
    return new Date(Date.UTC(year, leapDay.getUTCMonth(), leapDay.getUTCDate()));
  }

  // ECharts-Optionen für den Monatsvergleich der Energie: Monate auf der Achse, je Jahr eine Linie, Mittel und Spanne.
  // options: colors (cur, prev, text, grid, ink, surface), band (Spanne zeichnen), narrow (schmale Fläche), font (Schriftgröße).
  function energyMonthly(m, role, options) {
    const {colors} = options;
    const font = options.font || ((size) => size);
    const labels = Array.from({length: 12}, (_x, i) => monthName(i + 1, 'short'));
    const {past, avg, low, high, counts} = monthStats(role, m);
    const current = m.current.year;
    const lastPast = past[0];
    const hasAvg = counts.some((count) => count >= 2);
    const series = [];
    const legend = [];
    if (options.band && hasAvg) {
      series.push({
        name: 'low', type: 'line', stack: 'band', data: low, symbol: 'none', silent: true,
        lineStyle: {opacity: 0}, tooltip: {show: false},
      }, {
        name: 'band', type: 'line', stack: 'band', symbol: 'none', silent: true, lineStyle: {opacity: 0},
        data: high.map((top, i) => (top == null || low[i] == null ? null : top - low[i])),
        areaStyle: {color: colors.prev, opacity: 0.16},
      });
    }
    for (const year of past.slice().reverse()) {
      const strong = year === lastPast;
      const data = role.values[year].map((value, i) => (isPartialStart(role, year, i) ? null : value));
      series.push({
        name: String(year), type: 'line', data, symbol: 'none', connectNulls: false,
        lineStyle: {color: colors.prev, width: strong ? 2 : 1.2, opacity: strong ? 1 : 0.45},
        itemStyle: {color: colors.prev},
      });
      if (strong) legend.push(String(year));
    }
    if (hasAvg) {
      series.push({
        name: 'Ø', type: 'line', data: avg, symbol: 'none',
        lineStyle: {color: colors.text, width: 2, type: 'dashed'}, itemStyle: {color: colors.text},
      });
      legend.push('Ø');
    }
    if (role.values[current]) {
      // Der laufende Monat ist erst zum Teil vergangen und würde die Linie einbrechen lassen.
      const data = role.values[current].map((value, i) => (i + 1 >= m.current.month ? null : value));
      series.push({
        name: String(current), type: 'line', data, symbol: 'circle', symbolSize: 7, z: 5,
        lineStyle: {color: colors.cur, width: 3}, itemStyle: {color: colors.cur},
      });
      legend.unshift(String(current));
    }
    const cell = (value) => (value == null ? '–' : energy(value));
    return {
      animation: false,
      grid: {left: 8, right: 16, top: options.narrow ? 74 : 34, bottom: 8, containLabel: true},
      legend: {data: legend, top: 0, textStyle: {color: colors.text, fontSize: font(12)}, itemWidth: 18, itemHeight: 8},
      xAxis: {
        type: 'category', data: labels, boundaryGap: false,
        axisLine: {lineStyle: {color: colors.grid}}, axisTick: {show: false},
        axisLabel: {color: colors.text, fontSize: font(11)}, splitLine: {lineStyle: {color: colors.grid}},
      },
      yAxis: {
        type: 'value', name: t('kWh'), nameTextStyle: {color: colors.text},
        axisLine: {lineStyle: {color: colors.grid}}, axisTick: {show: false},
        axisLabel: {color: colors.text, fontSize: font(11)}, splitLine: {lineStyle: {color: colors.grid}},
      },
      tooltip: {
        trigger: 'axis', confine: true,
        backgroundColor: colors.surface, borderColor: colors.grid,
        textStyle: {color: colors.ink, fontSize: font(12)},
        formatter: (params) => {
          const i = params[0].dataIndex;
          const running = i + 1 === m.current.month;
          const now = role.values[current] ? role.values[current][i] : null;
          let html = `<b>${escapeHtml(monthName(i + 1, 'long'))}</b>`;
          html += `<br>${current}: ${cell(now)}${running && now != null ? ' ' + escapeHtml(t('(bisher)')) : ''}`;
          if (lastPast != null) html += `<br>${lastPast}: ${cell(role.values[lastPast][i])}`;
          if (avg[i] != null) html += `<br>Ø (${counts[i]}): ${cell(avg[i])}`;
          return html;
        },
      },
      series,
    };
  }

  // ECharts-Optionen für den Monatsvergleich des Wetters (Temperatur, Regen, Sonne). m: Antwort von monatsvergleich.
  function weatherMonthly(m, options) {
    const {colors} = options;
    const font = options.font || ((size) => size);
    const decimals = m.metric === 'temperature' ? 1 : (m.unit === 'min' || m.unit === 'h' ? 0 : 1);
    const labels = Array.from({length: 12}, (_x, i) => monthName(i + 1, 'short'));
    const yearKeys = Object.keys(m.years).map(Number).sort((a, b) => a - b);
    const current = String(m.current_year);
    const lastPast = yearKeys.filter((year) => year < m.current_year).pop();
    const hasAvg = m.counts.some((count) => count > 0);
    const series = [];
    const legend = [];
    if (options.band && hasAvg) {
      series.push({
        name: 'low', type: 'line', stack: 'band', data: m.low, symbol: 'none', silent: true,
        lineStyle: {opacity: 0}, tooltip: {show: false},
      }, {
        name: 'band', type: 'line', stack: 'band', symbol: 'none', silent: true, lineStyle: {opacity: 0},
        data: m.high.map((high, i) => (high == null || m.low[i] == null ? null : high - m.low[i])),
        areaStyle: {color: colors.prev, opacity: 0.16},
      });
    }
    for (const year of yearKeys) {
      if (year >= m.current_year) continue;
      const strong = year === lastPast;
      series.push({
        name: String(year), type: 'line', data: m.years[year], symbol: 'none', connectNulls: false,
        lineStyle: {color: colors.prev, width: strong ? 2 : 1.2, opacity: strong ? 1 : 0.45},
        itemStyle: {color: colors.prev},
      });
      if (strong) legend.push(String(year));
    }
    if (hasAvg) {
      series.push({
        name: 'Ø', type: 'line', data: m.avg, symbol: 'none',
        lineStyle: {color: colors.text, width: 2, type: 'dashed'}, itemStyle: {color: colors.text},
      });
      legend.push('Ø');
    }
    if (m.years[current]) {
      series.push({
        name: current, type: 'line', data: m.years[current], symbol: 'circle', symbolSize: 7, z: 5,
        lineStyle: {color: colors.cur, width: 3}, itemStyle: {color: colors.cur},
      });
      legend.unshift(current);
    }
    const unit = m.unit;
    return {
      animation: false, grid: gridFor(options.narrow), legend: legendBox(colors, legend, font),
      xAxis: {type: 'category', data: labels, boundaryGap: false, ...axisStyle(colors, font)},
      yAxis: {type: 'value', scale: m.metric === 'temperature', name: unit, nameTextStyle: {color: colors.text}, ...axisStyle(colors, font)},
      tooltip: tooltipBox(colors, font, (params) => {
        const i = params[0].dataIndex;
        const cell = (value) => (value == null ? '–' : `${num(value, decimals)} ${unit}`);
        const running = i === m.current_month - 1;
        let html = `<b>${escapeHtml(monthName(i + 1, 'long'))}</b>`;
        const now = m.years[current] ? m.years[current][i] : null;
        html += `<br>${current}: ${cell(now)}${running && now != null ? ' ' + escapeHtml(t('(bisher)')) : ''}`;
        if (lastPast != null) html += `<br>${lastPast}: ${cell(m.years[lastPast][i])}`;
        if (m.avg[i] != null) {
          html += `<br>Ø (${m.counts[i]}): ${cell(m.avg[i])}`;
          if (now != null && !running) html += `<br>${escapeHtml(t('Abweichung'))}: ${num(now - m.avg[i], decimals)} ${unit === '°C' ? 'K' : unit}`;
        }
        return html;
      }),
      series,
    };
  }

  // ECharts-Optionen der Jahresübersicht des Wetters (Jahre × 366 Tage als Heatmap). m: Antwort von matrix.
  // options: colors (cur, prev, cold, text, grid, ink, surface, sun, sunSoft, overcast), narrow, font.
  function weatherMatrix(m, options) {
    const {colors} = options;
    const font = options.font || ((size) => size);
    const isPrecip = m.metric === 'precip';
    const decimals = isPrecip && m.unit === 'min' ? 0 : 1;
    const unit = m.unit;
    const isSun = m.metric === 'sun';
    const inRange = isPrecip
      ? [colors.surface, colors.cold]
      : [colors.cold, colors.surface, colors.prev];
    const sunPieces = [
      {value: 2, label: t('sonnig'), color: colors.sun},
      {value: 1, label: t('wechselhaft'), color: colors.sunSoft},
      {value: 0, label: t('trüb'), color: colors.overcast},
    ];
    const hidden = {itemStyle: {borderWidth: 0}};
    return {
      animation: false,
      grid: {left: 8, right: 16, top: 6, bottom: 52, containLabel: true},
      xAxis: {
        type: 'category', data: Array.from({length: 366}, (_x, i) => i), splitArea: {show: false},
        axisLine: {lineStyle: {color: colors.grid}}, axisTick: {show: false},
        axisLabel: {
          color: colors.text, fontSize: font(11),
          interval: (index) => MONTH_STARTS_LEAP.includes(index),
          formatter: (_value, index) => monthName(leapSlotDate(index).month, options.narrow ? 'narrow' : 'short'),
        },
      },
      yAxis: {
        type: 'category', data: m.years.map(String), inverse: true,
        axisLine: {show: false}, axisTick: {show: false}, axisLabel: {color: colors.text, fontSize: font(11)},
      },
      visualMap: isSun ? {
        type: 'piecewise', pieces: sunPieces, seriesIndex: 1, orient: 'horizontal', left: 'center', bottom: 4,
        itemWidth: 14, itemHeight: 14, textStyle: {color: colors.text, fontSize: font(11)},
      } : {
        type: 'continuous', min: m.min, max: m.max, seriesIndex: 1, calculable: false, orient: 'horizontal',
        left: 'center', bottom: 4, itemWidth: 12, itemHeight: 140, inRange: {color: inRange},
        textStyle: {color: colors.text, fontSize: font(11)},
        text: [`${num(m.max, decimals)} ${unit}`, `${num(m.min, decimals)} ${unit}`],
      },
      tooltip: {
        confine: true, backgroundColor: colors.surface, borderColor: colors.grid,
        textStyle: {color: colors.ink, fontSize: font(12)},
        formatter: (param) => {
          const [slot, row, value] = param.data;
          const when = matrixDate(m.years[row], slot);
          const label = new Intl.DateTimeFormat(LOCALE, {day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC'}).format(when);
          if (param.seriesIndex === 0) return `<b>${escapeHtml(label)}</b><br>${escapeHtml(isSun ? t('Keine Tagesklasse') : t('Zu wenige Werte'))}`;
          if (isSun) {
            const hours = m.hours ? m.hours[when.toISOString().slice(0, 10)] : null;
            return `<b>${escapeHtml(label)}</b><br>${escapeHtml(sunPieces.find((piece) => piece.value === value).label)}`
              + (hours == null ? '' : `<br>${escapeHtml(num(hours, 1))} ${escapeHtml(t('Sonnenstunden'))}`);
          }
          return `<b>${escapeHtml(label)}</b><br>${escapeHtml(num(value, decimals))} ${escapeHtml(unit === '°C' ? '°C' : unit)}`;
        },
      },
      series: [
        {
          type: 'heatmap', data: m.missing.map(([slot, row]) => [slot, row, 0]), silent: false, ...hidden,
          itemStyle: {color: colors.grid, borderWidth: 0},
        },
        {type: 'heatmap', data: m.cells, ...hidden},
      ],
    };
  }

  window.ElementChartRender = {energyMonthly, weatherMonthly, weatherMatrix};
})();
