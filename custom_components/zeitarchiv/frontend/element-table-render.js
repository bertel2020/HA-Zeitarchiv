// Tabellen der Dashboards Energie und Wetter als HTML, ohne Alpine und ohne Seitenzustand (Roadmap 1.48).
// Aus energie-langzeit.js herausgelöst: dieselbe Tabelle zeichnet das Dashboard und die Lovelace-Karte
// (custom:zeitarchiv-card). Der Server rechnet (POST energiedashboard/langzeit/table), hier wird nur formatiert.
// Braucht t(), escapeHtml, NumberFormat und ServerTime als Globals sowie window.ZA_FORMAT (wie table-tile-render.js).
(() => {
  const LOCALE = window.ZA_FORMAT;
  const ZT = window.ServerTime;

  const formats = {
    dm: new Intl.DateTimeFormat(LOCALE, ZT.withZone({day: '2-digit', month: '2-digit'})),
    dmy: new Intl.DateTimeFormat(LOCALE, ZT.withZone({day: '2-digit', month: '2-digit', year: 'numeric'})),
    month: new Intl.DateTimeFormat(LOCALE, ZT.withZone({month: 'long'})),
    hm: new Intl.DateTimeFormat(LOCALE, ZT.withZone({hour: '2-digit', minute: '2-digit', hourCycle: 'h23'})),
    weekday: new Intl.DateTimeFormat(LOCALE, ZT.withZone({weekday: 'long'})),
  };
  const fmtDate = (format, ts) => format.format(new Date(ts * 1000));
  const num = (value, decimals) => NumberFormat.fmt(value, decimals);

  // Auswahl-Namen (relativ) — im Tabellenkopf steht stattdessen der konkrete Zeitraum.
  function columnName(key) {
    return {monat: t('Dieser Monat'), vormonat: t('Letzter Monat'), jahr: t('Dieses Jahr')}[key];
  }

  function columnTitle(col) {
    return col.key === 'jahr' ? t('Jahr') : fmtDate(formats.month, col.cur.start);
  }

  function sameDay(a, b) {
    const pa = ZT.parts(a), pb = ZT.parts(b);
    return pa.year === pb.year && pa.month === pb.month && pa.day === pb.day;
  }

  // "01.11. – 02.11.2026"; ein einzelner Tag ohne Bereich. Ende ist exklusiv, daher end - 1 s.
  function rangeText(start, end) {
    if (end <= start) return '';
    const last = end - 1;
    if (sameDay(start, last)) return fmtDate(formats.dmy, start);
    return `${fmtDate(formats.dm, start)} – ${fmtDate(formats.dmy, last)}`;
  }

  // Energie in kWh; ab 10.000 kWh als MWh. Kleine Werte mit einer Nachkommastelle, damit ein Monatsanfang
  // nicht als „2 kWh“ gegen „3 kWh“ erscheint.
  function energy(value) {
    if (Math.abs(value) >= 10000) return num(value / 1000, 1) + ' MWh';
    return num(value, Math.abs(value) < 100 ? 1 : 0) + ' kWh';
  }

  // Wert je Art der Zeile: kWh (energy), Prozent (pct, Differenz in Prozentpunkten) oder kWh je kWp (spec).
  function formatValue(row, value) {
    if (row.kind === 'pct') return num(value, 1) + '\u00a0%';
    if (row.kind === 'spec') return num(value, 1) + '\u00a0' + t('kWh/kWp');
    return energy(value);
  }

  // Differenz zum Vorjahr unter dem Wert; die Farbe sagt, ob die Änderung günstig ist (mehr Erzeugung
  // und Einspeisung, weniger Bezug und Verbrauch), nicht, ob die Zahl steigt oder fällt. Zeilen ohne Wertung
  // (Speicher) bleiben ungefärbt.
  function delta(cur, previous, row) {
    if (cur == null || previous == null) return '';
    const diff = cur - previous;
    const zero = Math.round(Math.abs(diff) * 10) === 0;
    let text = (zero ? '± ' : diff > 0 ? '▲ +' : '▼ −');
    // Die Einheit steht schon im Wert darüber; nur bei Prozentpunkten und MWh bleibt sie, damit die Zeile eindeutig ist.
    if (row.kind === 'pct') text += num(Math.abs(diff), 1) + ' ' + t('PP');
    else if (row.kind === 'spec') text += num(Math.abs(diff), 1);
    else text += Math.abs(diff) >= 10000 ? energy(Math.abs(diff)) : num(Math.abs(diff), Math.abs(diff) < 100 ? 1 : 0);
    // Prozentwerte vergleichen sich in Prozentpunkten, dort steht kein zweites Prozent daneben.
    if (row.kind !== 'pct' && previous !== 0 && !zero) {
      const percent = diff / previous * 100;
      text += ' (' + (percent > 0 ? '+' : '−') + num(Math.abs(percent), 0) + ' %)';
    }
    const good = !zero && row.better && (diff > 0) === (row.better === 'up');
    const cls = zero || !row.better ? '' : (good ? ' wt-dl-good' : ' wt-dl-bad');
    return `<span class="wt-dl${cls}">${escapeHtml(text)}</span>`;
  }

  function cellHtml(value, fromTs, vjCell, deltaHtml, row) {
    const cls = vjCell ? 'wt-vj' : 'wt-sep';
    if (value == null) {
      const title = fromTs ? ` title="${escapeHtml(t('Daten ab {date}', {date: fmtDate(formats.dmy, fromTs)}))}"` : '';
      return `<td class="wt-na ${cls}"${title}><span class="wt-v">–</span></td>`;
    }
    return `<td class="${cls}"><span class="wt-v">${formatValue(row, value)}</span>${deltaHtml || ''}</td>`;
  }

  function renderTable(data, showDiff) {
    const cols = data.columns;
    if (!cols.length) return `<tbody><tr><td>${escapeHtml(t('Keine Spalte ausgewählt.'))}</td></tr></tbody>`;
    const span = data.vorjahr ? 2 : 1;
    const year = (range) => String(ZT.parts(range.start).year);
    // Zwei Zeilen: Titel mit Info-Tooltip (Zeitraum), darunter das Jahr der Spalte und ihres Vorjahrs.
    let head = '<thead><tr><th></th>';
    let sub = '<tr class="wt-subhead"><th></th>';
    for (const col of cols) {
      head += `<th class="wt-cur wt-sep" data-tooltip-fixed="${escapeHtml(rangeText(col.cur.start, col.cur.end))}">${escapeHtml(columnTitle(col))}<span class="wt-info" aria-hidden="true">ⓘ</span></th>`;
      sub += `<th class="wt-cur wt-sep">${escapeHtml(year(col.cur))}</th>`;
      if (data.vorjahr) {
        head += `<th class="wt-vj" data-tooltip-fixed="${escapeHtml(rangeText(col.vj.start, col.vj.end))}">${escapeHtml(t('Vorjahr'))}</th>`;
        sub += `<th class="wt-vj">${escapeHtml(year(col.vj))}</th>`;
      }
    }
    let html = head + '</tr>' + sub + '</tr></thead><tbody>';
    let group = null;
    for (const row of data.rows) {
      if (row.group !== group) {
        group = row.group;
        html += `<tr class="wt-grp"><th colspan="${1 + cols.length * span}">${escapeHtml(group)}</th></tr>`;
      }
      html += `<tr><th scope="row">${escapeHtml(row.label)}</th>`;
      for (const col of cols) {
        const cell = row.cells[col.key] || {};
        const deltaHtml = showDiff && data.vorjahr ? delta(cell.cur, cell.vj, row) : '';
        html += cellHtml(cell.cur, cell.cur_from, false, deltaHtml, row);
        if (data.vorjahr) html += cellHtml(cell.vj, cell.vj_from, true, '', row);
      }
      html += '</tr>';
    }
    return html + '</tbody>';
  }
  const monthFormat = (style) => new Intl.DateTimeFormat(LOCALE, {month: style, timeZone: 'UTC'});
  const monthName = (month, style) => monthFormat(style).format(new Date(Date.UTC(2000, month - 1, 15)));
  const mean = (values) => values.reduce((a, b) => a + b, 0) / values.length;
  const present = (list) => list.filter((value) => value != null);
  const monthKey = (year, month) => `${year}-${String(month).padStart(2, '0')}`;

  // Mittel, Spanne und Anzahl je Monat über alle abgeschlossenen Jahre (mindestens zwei, sonst kein Vergleich).
  // Der Monat, in dem das Archiv mitten im Monat beginnt, ist nur zum Teil erfasst: er geht in kein Mittel ein.
  const isPartialStart = (role, year, index) => !!role.partial_start && role.partial_start[0] === year && role.partial_start[1] === index + 1;

  function monthStats(role, months) {
    const past = months.years.filter((year) => year < months.current.year);
    const avg = [], low = [], high = [], counts = [];
    for (let i = 0; i < 12; i++) {
      const values = present(past.filter((year) => !isPartialStart(role, year, i)).map((year) => role.values[year][i]));
      counts.push(values.length);
      const enough = values.length >= 2;
      avg.push(enough ? mean(values) : null);
      low.push(enough ? Math.min(...values) : null);
      high.push(enough ? Math.max(...values) : null);
    }
    return {past, avg, low, high, counts};
  }

  const yearSum = (list) => (list.every((value) => value != null) ? list.reduce((a, b) => a + b, 0) : null);

  // Jahre × Monate als HTML (Tabelle Reiter „Langzeit“). months: Antwort von langzeit/months mit den gewählten Jahren,
  // role: eine Rolle daraus. colors.good/bad/base färben die Abweichung zum Mittel; href(year, month) liefert den Link
  // in die Entität oder ''.
  function energyMatrix(m, role, {colors, href}) {
    const {avg, counts} = monthStats(role, m);
    const closed = m.years.filter((year) => year < m.current.year);
    const fullSums = closed.map((year) => yearSum(role.values[year])).filter((value) => value != null);
    const reference = fullSums.length >= 2 ? mean(fullSums) : null;
    const sign = (diff) => (Math.round(Math.abs(diff)) === 0 ? '±' : (diff > 0 ? '+' : '−')) + num(Math.abs(diff), 0) + ' %';
    const flagText = (flag) => {
      const parts = [];
      if (flag.gaps) parts.push(t('Messlücken: {n} (sonst etwa {typical})', {n: flag.gaps, typical: flag.gaps_typical || 0}));
      if (flag.counter_decreases) parts.push(t('Zählerrückgänge: {n}', {n: flag.counter_decreases}));
      return parts.join(', ');
    };
    const cell = (value, ref, tip, opts) => {
      if (value == null) return '<td class="wt-tm-na">–</td>';
      const attrs = (tip ? ` data-tooltip-fixed="${escapeHtml(tip)}"` : '');
      const klass = [opts.strong ? 'wt-tm-year' : '', opts.flag ? 'wt-tm-flag' : ''].filter(Boolean).join(' ');
      const inner = (opts.href
        ? (content) => `<a class="wt-tm-link" href="${escapeHtml(opts.href)}">${content}</a>`
        : (content) => content);
      if (ref == null) {
        return `<td class="wt-tm-plain ${klass}"${attrs}>${inner(escapeHtml(num(value, 0)))}</td>`;
      }
      const diff = (value - ref) / ref * 100;
      const favorable = role.better === 'up' ? diff > 0 : diff < 0;
      const share = Math.round(Math.min(1, Math.abs(diff) / 30) * 70);
      const style = ` style="background:color-mix(in srgb, ${favorable ? colors.good : colors.bad} ${share}%, ${colors.base})"`;
      return `<td${style}${attrs}${klass ? ` class="${klass}"` : ''}>${inner(
        `<span class="wt-tm-v">${escapeHtml(num(value, 0))}</span><span class="wt-tm-d">${escapeHtml(sign(diff))}</span>`)}</td>`;
    };
    let html = `<thead><tr><th></th>${Array.from({length: 12}, (_x, i) => `<th>${escapeHtml(monthName(i + 1, 'short'))}</th>`).join('')}`
      + `<th class="wt-tm-year">${escapeHtml(t('Jahr Σ'))}</th></tr></thead><tbody>`;
    for (const year of m.years) {
      const running = year === m.current.year;
      html += `<tr><th>${year}${running ? '*' : ''}</th>`;
      role.values[year].forEach((value, i) => {
        const month = i + 1;
        const flag = role.flags[monthKey(year, month)];
        let tip = value == null ? '' : `${monthName(month, 'short')} ${year}: ${energy(value)}`;
        if (value != null && avg[i] != null && !(running && month >= m.current.month) && !isPartialStart(role, year, i)) {
          const diff = (value - avg[i]) / avg[i] * 100;
          tip += ` (${sign(diff)} ${t('zum Mittel')})`;
        }
        if (running && month === m.current.month && value != null) tip += ' – ' + t('laufender Monat, noch nicht abgeschlossen');
        const partialStart = isPartialStart(role, year, i);
        if (partialStart && value != null) tip += ' – ' + t('das Archiv beginnt in diesem Monat');
        if (flag) tip += ' – ' + flagText(flag);
        const link = value == null ? '' : href(year, month);
        // Der laufende Monat ist noch nicht abgeschlossen und bekommt keinen Vergleich.
        const ref = (running && month >= m.current.month) || partialStart ? null : (counts[i] >= 2 ? avg[i] : null);
        html += cell(value, ref, tip, {flag: !!flag, href: link});
      });
      const total = yearSum(role.values[year]);
      const partial = present(role.values[year]);
      const sum = total != null ? total : (partial.length ? partial.reduce((a, b) => a + b, 0) : null);
      const complete = !running && total != null;
      const tipSum = sum == null ? '' : (complete ? t('Summe {year}: {value}', {year, value: energy(sum)})
        : t('Summe {year} bis jetzt: {value}', {year, value: energy(sum)}));
      html += cell(sum, complete ? reference : null, tipSum, {strong: true});
      html += '</tr>';
    }
    html += `<tr class="wt-tm-avg"><th>Ø</th>${avg.map((value, i) => `<td>${value == null ? '–' : escapeHtml(num(value, 0))}</td>`).join('')}`
      + `<td class="wt-tm-year">${reference == null ? '–' : escapeHtml(num(reference, 0))}</td></tr></tbody>`;
    return html;
  }

  // ---- Wetterdashboard: Vergleichstabelle (aus wetter.js herausgelöst) ----
  const WIND_KEYS = ['wind', 'gust', 'radiation', 'illuminance'];
  const groupOf = (key) => (WIND_KEYS.includes(key) ? 'wind' : (key.includes(':') ? 'klima' : 'basis'));
  const inGroup = (key, group) => groupOf(key) === group;

  function weatherColumnTitle(col, data) {
    // Mit Stichtag stehen „Heute“ und „Gestern“ für andere Tage: dann das Datum selbst.
    if (data && data.at && (col.key === 'heute' || col.key === 'gestern')) return fmtDate(formats.dmy, col.cur.start);
    if (col.key === 'heute') return t('Heute');
    if (col.key === 'gestern') return t('Gestern');
    if (col.key === 'jahr') return t('Jahr');
    return fmtDate(formats.month, col.cur.start);
  }

  function weatherDelta(cur, previous, unit, decimals, withPercent) {
    if (cur == null || previous == null) return '';
    const diff = cur - previous;
    const zero = Math.round(Math.abs(diff) * Math.pow(10, decimals)) === 0;
    let text = (zero ? '± ' : diff > 0 ? '▲ +' : '▼ −') + num(Math.abs(diff), decimals);
    // Die Einheit steht schon am Wert; nur „K“ bleibt, weil sie von „°C“ abweicht. Kürzer = schmalere Spalte.
    if (unit === 'K') text += ' K';
    if (withPercent && previous !== 0 && !zero) {
      const percent = diff / previous * 100;
      text += ' (' + (percent > 0 ? '+' : '−') + num(Math.abs(percent), 0) + ' %)';
    }
    return `<span class="wt-dl">${escapeHtml(text)}</span>`;
  }

  // Kennzahl-Zeilen je Art der Rolle. when: 'point' = Zeitpunkt (Stunde bzw. Datum),
  // 'day' = ganzer Tag (in Tagesspalten ohne Zusatz).
  function metricsFor(row, data) {
    if (row.kind === 'kenntage') {
      return [
        {label: t('Frosttage'), field: 'frost', decimals: 0, unit: '', delta: true},
        {label: t('Eistage'), field: 'eis', decimals: 0, unit: '', delta: true},
        {label: t('Sommertage'), field: 'sommer', decimals: 0, unit: '', delta: true},
        {label: t('Heiße Tage'), field: 'heiss', decimals: 0, unit: '', delta: true},
      ];
    }
    if (row.kind === 'standard') {
      // Strahlung fällt nachts auf 0: ein Minimum sagt dort nichts, Max und Ø genügen.
      const minimum = row.key === 'radiation' ? [] : [{label: t('Min'), field: 'min', when: 'point', delta: true}];
      return [
        {label: t('Max'), field: 'max', when: 'point', delta: true},
        ...minimum,
        {label: 'Ø', field: 'avg', delta: true},
      ];
    }
    if (row.kind === 'sunshine') {
      // Stundengenau: Stunden, deren Mittel die Schwelle erreicht. Die Schwelle steht in der Beschriftung.
      return [
        {label: t('Sonnenstunden (ab {n} lx)', {n: num(data.sun_threshold_lx, 0)}), field: 'hours', decimals: 1, unit: 'h', delta: true, percent: true},
        {label: t('Sonnigster Tag'), field: 'top', decimals: 1, unit: 'h', when: 'day'},
      ];
    }
    if (row.kind === 'counter') {
      return [
        {label: t('Summe'), field: 'sum', decimals: 1, delta: true, percent: true},
        {label: t('Regentage (ab {n} mm)', {n: num(data.rain_day_mm, 1)}), field: 'days', decimals: 0, unit: ''},
        {label: t('Nassester Tag'), field: 'top', decimals: 1, when: 'day'},
      ];
    }
    return [
      {label: t('Regenminuten'), field: 'minutes', decimals: 0, unit: 'min', delta: true, percent: true},
      {label: t('Regentage (ab {n} min)', {n: num(data.rain_day_minutes, 0)}), field: 'days', decimals: 0, unit: ''},
      {label: t('Regenreichster Tag'), field: 'top', decimals: 0, unit: 'min', when: 'day'},
    ];
  }

  // Zusatz in Klammern („(ab 10 min)“) klein und gedämpft hinter dem Namen: hält die erste Spalte schmal.
  function metricLabelHtml(label) {
    const i = label.indexOf(' (');
    if (i < 0) return escapeHtml(label);
    return `${escapeHtml(label.slice(0, i))} <small class="wt-qual">${escapeHtml(label.slice(i + 1))}</small>`;
  }

  function whenText(metric, summary, col) {
    if (!metric.when || !summary) return '';
    const ts = summary[metric.field + '_ts'];
    if (ts == null) return '';
    if (col.range === 'day') {
      // Die Werte stammen aus Stundenzeilen: „0–1 Uhr“ ist ehrlicher als eine Minutenangabe wie „00:00“.
      if (metric.when !== 'point') return '';
      const hour = ZT.parts(ts).hour;
      return t('{from}–{to} Uhr', {from: hour, to: hour + 1});
    }
    return fmtDate(formats.dm, ts);
  }

  function weatherCell(summary, fromTs, metric, row, col, vjCell, deltaHtml) {
    const cls = (vjCell ? 'wt-vj' : 'wt-sep');
    if (!summary || summary[metric.field] == null) {
      const title = fromTs ? ` title="${escapeHtml(t('Daten ab {date}', {date: fmtDate(formats.dmy, fromTs)}))}"` : '';
      return `<td class="wt-na ${cls}"${title}><span class="wt-v">–</span></td>`;
    }
    const decimals = metric.decimals != null ? metric.decimals : (row.decimals != null ? row.decimals : 1);
    const unit = metric.unit != null ? metric.unit : row.unit;
    // Tag von Max/Min in Zeitraum-Spalten als eigene kleine Zeile unter dem Wert; in Tagesspalten steht die Stunde
    // im Tooltip der Zelle (data-tooltip-fixed, fixed-tooltip.js).
    const when = whenText(metric, summary, col);
    const inline = col.range !== 'day' && when;
    const tip = when && !inline ? ` data-tooltip-fixed="${escapeHtml(when)}"` : '';
    return `<td class="${cls}"${tip}><span class="wt-v">${escapeHtml(num(summary[metric.field], decimals))}${unit ? '&nbsp;' + escapeHtml(unit) : ''}</span>`
      + (inline ? `<span class="wt-when">${escapeHtml(when)}</span>` : '') + (deltaHtml || '') + '</td>';
  }


  function weatherComparison(data, group, showDiff) {
    const cols = data.columns;
    if (!cols.length) return `<tbody><tr><td>${escapeHtml(t('Keine Spalte ausgewählt.'))}</td></tr></tbody>`;
    const span = data.vorjahr ? 2 : 1;
    if (!data.rows.some((r) => inGroup(r.key, group))) {
      return `<tbody><tr><td class="wt-empty">${escapeHtml(t('Alle Blöcke dieser Gruppe sind in der Einrichtung ausgeblendet.'))}</td></tr></tbody>`;
    }
    // Zwei Zeilen: Titel mit Info-Tooltip (Zeitraum, „bis 15:47“), darunter Tag bzw. Jahr der Spalte und ihres Vorjahrs.
    // Mit Stichtag steht das Datum schon im Titel; die zweite Zeile nennt dann den Wochentag.
    const subText = (range, key) => {
      if (key === 'heute' || key === 'gestern') return fmtDate(formats.dmy, range.start);
      return String(ZT.parts(range.start).year);
    };
    let head = '<thead><tr><th></th>';
    let sub = '<tr class="wt-subhead"><th></th>';
    for (const col of cols) {
      let tip = rangeText(col.cur.start, col.cur.end);
      const dayCol = col.key === 'heute' || col.key === 'gestern';
      if (col.key === 'heute' && !data.at) tip = t('bis {time}', {time: fmtDate(formats.hm, data.now)});
      if (data.at && dayCol) tip = fmtDate(formats.weekday, col.cur.start);
      head += `<th class="wt-cur wt-sep" data-tooltip-fixed="${escapeHtml(tip)}">${escapeHtml(weatherColumnTitle(col, data))}<span class="wt-info" aria-hidden="true">ⓘ</span></th>`;
      const curSub = data.at && dayCol ? fmtDate(formats.weekday, col.cur.start) : subText(col.cur, col.key);
      sub += `<th class="wt-cur wt-sep">${escapeHtml(curSub)}</th>`;
      if (data.vorjahr) {
        head += `<th class="wt-vj" data-tooltip-fixed="${escapeHtml(rangeText(col.vj.start, col.vj.end))}">${escapeHtml(t('Vorjahr'))}</th>`;
        sub += `<th class="wt-vj">${escapeHtml(subText(col.vj, col.key))}</th>`;
      }
    }
    let html = head + '</tr>' + sub + '</tr>';
    html += '</thead><tbody>';

    for (const row of data.rows.filter((r) => inGroup(r.key, group))) {
      html += `<tr class="wt-grp"><th colspan="${1 + cols.length * span}">${escapeHtml(row.label)}</th></tr>`;
      for (const metric of metricsFor(row, data)) {
        html += `<tr><th scope="row">${metricLabelHtml(metric.label)}</th>`;
        for (const col of cols) {
          const cell = row.cells[col.key] || {};
          const decimals = metric.decimals != null ? metric.decimals : (row.decimals != null ? row.decimals : 1);
          const unit = metric.unit != null ? metric.unit : (row.unit === '°C' ? 'K' : row.unit);
          const deltaHtml = showDiff && data.vorjahr && metric.delta && cell.cur && cell.vj
            ? weatherDelta(cell.cur[metric.field], cell.vj[metric.field], unit, decimals, !!metric.percent) : '';
          html += weatherCell(cell.cur, cell.cur_from, metric, row, col, false, deltaHtml);
          if (data.vorjahr) html += weatherCell(cell.vj, cell.vj_from, metric, row, col, true, '');
        }
        html += '</tr>';
      }
    }
    return html + '</tbody>';
  }

  window.ElementTableRender = {
    weatherComparison, WIND_KEYS, groupOf, inGroup,
    formats, fmtDate, rangeText, energy, columnName, energyComparison: renderTable,
    monthName, mean, present, monthKey, isPartialStart, monthStats, yearSum, energyMatrix,
  };
})();
