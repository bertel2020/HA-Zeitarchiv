// Kennzahlen-Kacheln der Dashboards Energie und Wetter als HTML, ohne Alpine und ohne Seitenzustand (Roadmap 1.48, P3).
// Für die Lovelace-Karte (custom:zeitarchiv-card): die App liefert Werte, Vorperiode und Verlauf (card_elements.py), hier
// wird formatiert und der Verlauf als SVG gezeichnet, ohne ECharts. Alles, was aus der App stammt (Beschriftung, Einheit),
// wird maskiert. Braucht t(), escapeHtml und NumberFormat als Globals (wie element-table-render.js).
(() => {
  const num = (value, decimals) => NumberFormat.fmt(value, decimals);

  // Der Verlauf als Linie; Lücken (null) trennen die Linie. Die Farbe kommt aus der Umgebung (currentColor).
  function sparkline(values) {
    const points = (values || []).map((value) => (typeof value === 'number' && Number.isFinite(value) ? value : null));
    const present = points.filter((value) => value != null);
    if (present.length < 2) return '';
    const W = 120;
    const H = 26;
    const pad = 2;
    const min = Math.min(...present);
    const max = Math.max(...present);
    const span = max - min || 1;
    const x = (index) => (points.length === 1 ? W / 2 : pad + (index * (W - 2 * pad)) / (points.length - 1));
    const y = (value) => H - pad - ((value - min) / span) * (H - 2 * pad);
    const lines = [];
    let current = [];
    points.forEach((value, index) => {
      if (value == null) {
        if (current.length) lines.push(current);
        current = [];
      } else {
        current.push(`${x(index).toFixed(1)},${y(value).toFixed(1)}`);
      }
    });
    if (current.length) lines.push(current);
    const paths = lines.filter((line) => line.length > 1)
      .map((line) => `<polyline points="${line.join(' ')}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>`);
    return `<svg class="kpi-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${paths.join('')}</svg>`;
  }

  // Änderung zur Vorperiode: Prozent, sonst absolut; die Farbe sagt, ob sie günstig ist, nicht, ob die Zahl steigt.
  function delta(item, compareLabel) {
    const pct = typeof item.pct === 'number' ? item.pct : null;
    const abs = typeof item.abs === 'number' ? item.abs : null;
    if (pct == null && abs == null) return '';
    const change = pct != null ? pct : abs;
    const zero = Math.round(Math.abs(change) * 10) === 0;
    const text = (zero ? '± ' : change > 0 ? '▲ +' : '▼ −') + (pct != null ? `${num(Math.abs(pct), 0)} %` : `${num(Math.abs(abs), 1)} ${item.delta_unit || item.unit || ''}`);
    const good = !zero && item.better && (change > 0) === (item.better === 'up');
    const cls = zero || !item.better ? '' : (good ? ' kpi-good' : ' kpi-bad');
    return `<span class="kpi-delta${cls}">${escapeHtml(text)}${compareLabel ? ` <small>${escapeHtml(compareLabel)}</small>` : ''}</span>`;
  }

  function tile(label, valueHtml, subHtml, sparkHtml) {
    return `<div class="kpi-tile"><div class="kpi-label">${escapeHtml(label)}</div><div class="kpi-value">${valueHtml}</div>`
      + `${subHtml || ''}${sparkHtml || ''}</div>`;
  }

  const unitHtml = (unit) => (unit ? `<span class="kpi-unit">${escapeHtml(unit)}</span>` : '');

  // Energie: items aus card_elements (key, label, unit, value, pct, abs, better, spark).
  function energyKpis(items, options = {}) {
    if (!items || !items.length) return `<div class="kpi-empty">${escapeHtml(t('Keine Spalte ausgewählt.'))}</div>`;
    const tiles = items.map((item) => {
      const change = delta(item, options.compareLabel);
      // Zeilen unter dem Wert (Speicher: Ladestand, Ladung, Entladung); Beschriftung und Einheit kommen aus der App.
      const lines = (item.lines || []).map((line) => `<div class="kpi-sub">${escapeHtml(line.label)} ${escapeHtml(num(line.value, Math.abs(line.value) < 100 ? 1 : 0))}\u00a0${escapeHtml(line.unit || '')}</div>`).join('');
      return tile(
        item.label,
        item.value == null ? '–' : `${escapeHtml(num(item.value, Math.abs(item.value) < 100 ? 1 : 0))}${unitHtml(item.unit)}`,
        (change ? `<div class="kpi-sub">${change}</div>` : '') + lines,
        sparkline(item.spark),
      );
    });
    return `<div class="kpi-grid">${tiles.join('')}</div>`;
  }

  // Wetter: Kacheln des Dashboards (key, label, unit, decimals, kind, last, today, yesterday). Der Wert hängt an der Art:
  // Messwerte zeigen den letzten Wert mit Höchst- und Tiefstwert, Zähler und Dauern die Summe des Tages mit dem Vortag.
  function weatherKpis(tiles) {
    if (!tiles || !tiles.length) return `<div class="kpi-empty">${escapeHtml(t('Keine Spalte ausgewählt.'))}</div>`;
    const html = tiles.map((entry) => {
      const today = entry.today || {};
      const yesterday = entry.yesterday || {};
      const decimals = Number.isInteger(entry.decimals) ? entry.decimals : 1;
      let value;
      let unit = entry.unit || '';
      let sub = '';
      if (entry.kind === 'sunshine') {
        value = today.hours;
        unit = 'h';
        if (yesterday.hours != null) sub = `${t('Gestern')}: ${num(yesterday.hours, 1)} h`;
      } else if (entry.kind === 'counter' || entry.kind === 'switch') {
        value = today.sum;
        if (yesterday.sum != null) sub = `${t('Gestern')}: ${num(yesterday.sum, decimals)}${unit ? ` ${unit}` : ''}`;
      } else if (today.minutes != null) {
        value = today.minutes;
        unit = unit || 'min';
        if (yesterday.minutes != null) sub = `${t('Gestern')}: ${num(yesterday.minutes, 0)} ${unit}`;
      } else {
        value = entry.last;
        const parts = [];
        if (today.max != null) parts.push(`${t('Max')} ${num(today.max, decimals)}`);
        if (today.min != null) parts.push(`${t('Min')} ${num(today.min, decimals)}`);
        sub = parts.join(' · ');
      }
      return tile(
        entry.label,
        value == null ? '–' : `${escapeHtml(num(value, decimals))}${unitHtml(unit)}`,
        sub ? `<div class="kpi-sub">${escapeHtml(sub)}</div>` : '',
        '',
      );
    });
    return `<div class="kpi-grid">${html.join('')}</div>`;
  }

  // Rekorde: je ein Kachel mit dem höchsten Tageswert und dem Datum. Sie gibt es erst nach einem Jahr Archiv (enough).
  function energyRecords(data) {
    const records = data.records || [];
    if (!data.enough || !records.length) return `<div class="kpi-empty">${escapeHtml(t('Rekorde erscheinen, sobald ein Jahr Daten vorliegt.'))}</div>`;
    const {formats, fmtDate} = window.ElementTableRender;
    const tiles = records.map((record) => {
      const date = fmtDate(formats.dmy, Date.parse(`${record.date}T12:00:00Z`) / 1000);
      return tile(record.label, `${escapeHtml(num(record.value, record.value < 100 ? 1 : 0))}${unitHtml(data.unit)}`,
        `<div class="kpi-sub">${escapeHtml(date)}</div>`, '');
    });
    return `<div class="kpi-grid">${tiles.join('')}</div>`;
  }

  window.ElementKpiRender = {energyKpis, weatherKpis, sparkline, energyRecords};
})();
