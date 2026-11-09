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
    return {heute: t('Heute'), gestern: t('Gestern'), monat: t('Dieser Monat'), vormonat: t('Letzter Monat'), jahr: t('Dieses Jahr')}[key];
  }

  const isDayKey = (key) => key === 'heute' || key === 'gestern';
  // Einzelnes Jahr im Wetterdashboard: „j2024“.
  const isYearKey = (key) => /^j\d{4}$/.test(key);

  // Mit Stichtag stehen „Heute“ und „Gestern“ für andere Tage: dann das Datum selbst (wie im Wetterdashboard).
  function columnTitle(col, data) {
    if (isDayKey(col.key)) return data && data.at ? fmtDate(formats.dmy, col.cur.start) : columnName(col.key);
    return col.key === 'jahr' || isYearKey(col.key) ? t('Jahr') : fmtDate(formats.month, col.cur.start);
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

  // Kopf der Vergleichstabellen, zwei Zeilen: Titel mit Info-Tooltip (Zeitraum), darunter Tag bzw. Jahr der Spalte und ihres
  // Vorjahrs. Das Dashboard der Verbraucher teilt ihn mit der Summen-Tabelle. data: {columns, vorjahr, at, now}; eine Spalte
  // kann Titel, Untertitel und Tooltips selbst mitbringen (title, sub, tip, vjSub, vjTip), etwa ein einzelnes Jahr.
  // corner: {title, sub} der ersten Spalte (HTML, schon maskiert); titleHtml(col, html) umhüllt den Titel, etwa mit einem
  // Sortierknopf.
  function comparisonHead(data, {corner = {}, titleHtml = null} = {}) {
    // Tage zeigen ihr Datum, alle anderen Zeiträume das Jahr.
    const year = (range, key) => (isDayKey(key) ? fmtDate(formats.dmy, range.start) : String(ZT.parts(range.start).year));
    let head = `<thead><tr><th>${corner.title || ''}</th>`;
    let sub = `<tr class="wt-subhead"><th>${corner.sub || ''}</th>`;
    for (const col of data.columns) {
      let tip = col.tip != null ? col.tip : rangeText(col.cur.start, col.cur.end);
      if (col.tip == null && col.key === 'heute' && !data.at) tip = t('bis {time}', {time: fmtDate(formats.hm, data.now)});
      if (col.tip == null && data.at && isDayKey(col.key)) tip = fmtDate(formats.weekday, col.cur.start);
      const title = escapeHtml(col.title != null ? col.title : columnTitle(col, data));
      const subCur = col.sub != null ? col.sub : (data.at && isDayKey(col.key) ? fmtDate(formats.weekday, col.cur.start) : year(col.cur, col.key));
      head += `<th class="wt-cur wt-sep${col.headClass || ''}"${col.headAttrs || ''} data-tooltip-fixed="${escapeHtml(tip)}">${titleHtml ? titleHtml(col, title) : title}<span class="wt-info" aria-hidden="true">ⓘ</span></th>`;
      sub += `<th class="wt-cur wt-sep${col.headClass || ''}">${escapeHtml(subCur)}</th>`;
      if (data.vorjahr) {
        const vjTip = col.vjTip != null ? col.vjTip : rangeText(col.vj.start, col.vj.end);
        const vjSub = col.vjSub != null ? col.vjSub : year(col.vj, col.key);
        head += `<th class="wt-vj" data-tooltip-fixed="${escapeHtml(vjTip)}">${escapeHtml(t('Vorjahr'))}</th>`;
        sub += `<th class="wt-vj">${escapeHtml(vjSub)}</th>`;
      }
    }
    return head + '</tr>' + sub + '</tr></thead>';
  }

  function renderTable(data, showDiff) {
    const cols = data.columns;
    if (!cols.length) return `<tbody><tr><td>${escapeHtml(t('Keine Spalte ausgewählt.'))}</td></tr></tbody>`;
    const span = data.vorjahr ? 2 : 1;
    let html = comparisonHead(data) + '<tbody>';
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
    if (col.key === 'jahr' || isYearKey(col.key)) return t('Jahr');
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


  function weatherComparison(data, group, showDiff, opts = {}) {
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

    const span2 = 1 + cols.length * span;
    // Eine Zeilengruppe: Kopf (Name des Blocks) und je Kennzahl eine Zeile. label überschreibt den Namen der Kennzahl.
    const metricRows = (row, metrics, label) => {
      let out = '';
      for (const metric of metrics) {
        out += `<tr><th scope="row">${label ? escapeHtml(label) : metricLabelHtml(metric.label)}</th>`;
        for (const col of cols) {
          const cell = row.cells[col.key] || {};
          const decimals = metric.decimals != null ? metric.decimals : (row.decimals != null ? row.decimals : 1);
          const unit = metric.unit != null ? metric.unit : (row.unit === '°C' ? 'K' : row.unit);
          const deltaHtml = showDiff && data.vorjahr && metric.delta && cell.cur && cell.vj
            ? weatherDelta(cell.cur[metric.field], cell.vj[metric.field], unit, decimals, !!metric.percent) : '';
          out += weatherCell(cell.cur, cell.cur_from, metric, row, col, false, deltaHtml);
          if (data.vorjahr) out += weatherCell(cell.vj, cell.vj_from, metric, row, col, true, '');
        }
        out += '</tr>';
      }
      return out;
    };
    const shown = data.rows.filter((r) => inGroup(r.key, group));
    // Weitere Sensoren mit Raum: ein Block je Raum, darin Temperatur und Feuchte (Roadmap 1.51). Ohne Raum bei allen
    // Sensoren bleibt es beim Block je Sensor. Reihenfolge der Räume wie die der Einträge, „Ohne Raum“ zuletzt.
    if (group === 'klima' && shown.some((r) => r.room)) {
      const rooms = new Map();
      for (const row of shown) {
        const name = row.room || '';
        if (!rooms.has(name)) rooms.set(name, []);
        rooms.get(name).push(row);
      }
      const names = [...rooms.keys()].filter(Boolean).concat(rooms.has('') ? [''] : []);
      const kind = (row) => (row.unit === '%' ? t('Feuchte') : t('Temperatur'));
      const roomBlock = (name) => {
        const list = rooms.get(name);
        const roomClosed = (opts.closedRooms || []).includes(name);
        const roomTitle = escapeHtml(name || t('Ohne Raum'));
        let block = opts.interactive
          ? `<tr class="wt-grp wt-room is-toggle${roomClosed ? ' is-closed' : ''}"><th colspan="${span2}" data-room="${escapeHtml(name)}" role="button" tabindex="0" aria-expanded="${!roomClosed}">`
            + `<span class="wt-floor-chev" aria-hidden="true">▾</span> ${roomTitle}</th></tr>`
          : `<tr class="wt-grp"><th colspan="${span2}">${roomTitle}</th></tr>`;
        if (roomClosed) return block;
        // Zwei Sensoren gleicher Art im Raum: der Name des Eintrags unterscheidet sie.
        const kinds = list.map(kind);
        const label = (row, i) => (!name || kinds.indexOf(kinds[i]) !== i || kinds.lastIndexOf(kinds[i]) !== i ? row.label : kinds[i]);
        list.forEach((row, i) => {
          const metrics = metricsFor(row, data);
          const wanted = opts.avgOnly ? metrics.filter((m) => m.field === 'avg') : metrics;
          const title = label(row, i);
          if (opts.avgOnly) block += metricRows(row, wanted, `${title} Ø`);
          else {
            if (list.length > 1 || !name) block += `<tr class="wt-sub"><th colspan="${span2}">${escapeHtml(title)}</th></tr>`;
            block += metricRows(row, wanted);
          }
        });
        return block;
      };
      // Etagen aus Home Assistant: Räume unter ihrer Etage, Etage und Raum lassen sich einklappen (opts.closedFloors, opts.closedRooms).
      // Ohne Etage bei allen Räumen entfallen die Köpfe. Räume ohne Etage stehen zuletzt unter „Ohne Etage“.
      const floorOf = (name) => (name ? (rooms.get(name)[0].floor || '') : '');
      if (!names.some((name) => floorOf(name))) {
        for (const name of names) html += roomBlock(name);
        return html + '</tbody>';
      }
      const floors = [];
      for (const name of names) if (floorOf(name) && !floors.includes(floorOf(name))) floors.push(floorOf(name));
      if (names.some((name) => !floorOf(name))) floors.push('');
      const closed = opts.closedFloors || [];
      for (const floor of floors) {
        const inFloor = names.filter((name) => floorOf(name) === floor);
        const isClosed = closed.includes(floor);
        const attrs = opts.interactive
          ? ` data-floor="${escapeHtml(floor)}" role="button" tabindex="0" aria-expanded="${!isClosed}"` : '';
        html += `<tr class="wt-floor${isClosed ? ' is-closed' : ''}${opts.interactive ? ' is-toggle' : ''}"><th colspan="${span2}"${attrs}>`
          + `<span class="wt-floor-chev" aria-hidden="true">▾</span> ${escapeHtml(floor || t('Ohne Etage'))}</th></tr>`;
        if (!isClosed) for (const name of inFloor) html += roomBlock(name);
      }
      return html + '</tbody>';
    }
    for (const row of shown) {
      html += `<tr class="wt-grp"><th colspan="${span2}">${escapeHtml(row.label)}</th></tr>`;
      const metrics = metricsFor(row, data);
      html += metricRows(row, opts.avgOnly && group === 'klima' ? metrics.filter((m) => m.field === 'avg') : metrics,
        opts.avgOnly && group === 'klima' ? 'Ø' : '');
    }
    return html + '</tbody>';
  }

  // ---- Kenntage je Jahr und „Was hat sich verändert?“ (Energie, Langzeit) -------------------------
  // Kenntage: Beschriftung, Regel und die Zeile je Jahr. Die Schwellen kommen aus dem Setup der App.
  const KENNTAG_GROUPS = () => ({eigenversorgung: t('Eigenversorgung'), erzeugung: t('Erzeugung'), speicher: t('Speicher')});
  const KENNTAG_LABELS = () => ({
    fast_autark: t('Fast autark'), ohne_netz: t('Tage ohne Netzbezug'), ueberschuss: t('Überschusstage'),
    einspeisung_hoch: t('Hohe Einspeisung'), sonnig: t('Sonnentage'), truebe: t('Trübe Tage'),
    speicher_stark: t('Speicher stark genutzt'), speicher_schwach: t('Speicher kaum genutzt'),
  });

  const KENNTAG_RULES = {
    fast_autark: (th) => t('Autarkie ab {value} %', {value: num(th.autark, 0)}),
    ohne_netz: () => t('Netzbezug höchstens 0,1 kWh'),
    ueberschuss: () => t('mehr Einspeisung als Verbrauch'),
    einspeisung_hoch: (th) => t('mehr als {value} kWh am Tag eingespeist', {value: num(th.einspeisung, 0)}),
    sonnig: (th) => t('ab {value} kWh je kWp', {value: num(th.sonnig, 1)}),
    truebe: (th) => t('unter {value} % des Tagesmittels', {value: num(th.truebe, 0)}),
    speicher_stark: (th) => t('ab {value} % der Kapazität', {value: num(th.speicher_stark, 0)}),
    speicher_schwach: (th) => t('unter {value} % der Kapazität', {value: num(th.speicher_schwach, 0)}),
  };

  const kenntagRule = (key, th) => (KENNTAG_RULES[key] || KENNTAG_RULES.speicher_schwach)(th);

  // Ein Feld je Kenntag, darin ein Balken je Jahr (Länge = Anteil an den ausgewerteten Tagen, Maßstab je Feld).
  // interactive: die Zeilen sind Schaltflächen (Jahreskalender im Dashboard); die Karte zeichnet reine Zeilen.
  function energyKenntage(kt, {ytd, years, current, interactive}) {
    const shownYears = years ? kt.years.slice(0, years) : kt.years;
    const groups = KENNTAG_GROUPS();
    const labels = KENNTAG_LABELS();
    const tag = interactive ? 'button type="button"' : 'div';
    const close = interactive ? 'button' : 'div';
    let html = '';
    let lastGroup = null;
    for (const key of kt.available) {
      const group = kt.groups[key];
      if (group !== lastGroup) html += `<div class="wt-kt-group">${escapeHtml(groups[group])}</div>`;
      lastGroup = group;
      // Die Speicher-Kenntage zeigen ein Jahr ohne Speicher (kein Tag auswertbar) als „kein Speicher“ statt es wegzulassen.
      const storage = key.startsWith('speicher');
      const rows = shownYears.map((entry) => {
        const f = entry.fields[key];
        const days = ytd ? f.days_ytd : f.days;
        const hit = ytd ? f.hit_ytd : f.hit;
        return {year: entry.year, days, hit, pct: days ? hit / days * 100 : 0, none: storage && f.days === 0};
      }).filter((row) => row.days > 0 || row.none);
      const top = Math.max(0, ...rows.map((row) => row.pct));
      html += `<div class="wt-kt-col"><h3 class="wt-kt-title">${escapeHtml(labels[key])}</h3>`
        + `<p class="wt-kt-rule">${escapeHtml(kenntagRule(key, kt.thresholds))}</p>`;
      for (const row of rows) {
        if (row.none) {
          html += `<div class="wt-kt-row wt-kt-none"><span class="wt-kt-year">${row.year}${row.year === current ? '*' : ''}</span>`
            + `<span class="wt-kt-bar"></span><span class="wt-kt-val">${escapeHtml(t('kein Speicher'))}</span></div>`;
          continue;
        }
        const pct = row.hit > 0 && row.pct < 1 ? '< 1 %' : `${num(row.pct, 0)} %`;
        const tip = `${t('Ausgewertete Tage')}: ${num(row.days, 0)}`;
        const data = interactive ? ` data-field="${key}" data-year="${row.year}"` : '';
        html += `<${tag} class="wt-kt-row"${data} data-tooltip-fixed="${escapeHtml(tip)}">`
          + `<span class="wt-kt-year">${row.year}${row.year === current ? '*' : ''}</span>`
          + `<span class="wt-kt-bar"><i style="width:${top > 0 ? (row.pct / top * 100).toFixed(1) : 0}%"></i></span>`
          + `<span class="wt-kt-val"><b>${escapeHtml(num(row.hit, 0))}</b> ${escapeHtml(t('Tage'))} · ${escapeHtml(pct)}</span></${close}>`;
      }
      html += '</div>';
    }
    return html;
  }

  // „Was hat sich verändert?“: Balken nach links (weniger) und rechts (mehr) von der Mitte, rot ist mehr Verbrauch.
  // links: die Verbraucher werden zu Verweisen auf ihre Entität (nur in der App).
  function energyChanges(c, {links}) {
    const peak = Math.max(...c.items.map((item) => Math.abs(item.diff)), 0.0001);
    return c.items.map((item) => {
      const more = item.diff > 0;
      const width = Math.max(1, Math.round(Math.abs(item.diff) / peak * 48));
      const side = more ? `left:50%;width:${width}%` : `right:50%;width:${width}%`;
      const color = more ? 'var(--danger)' : 'var(--positive)';
      const percent = item.percent == null ? '' : ` (${item.percent > 0 ? '+' : '−'}${num(Math.abs(item.percent), 0)} %)`;
      const text = (more ? '▲ +' : '▼ −') + energy(Math.abs(item.diff)) + percent;
      const name = links && item.entity_id
        ? `<a href="entities/${encodeURIComponent(item.entity_id)}">${escapeHtml(item.name)}</a>` : escapeHtml(item.name);
      return `<div class="wt-chg-row"><span class="wt-chg-name">${name}</span>`
        + `<div class="wt-chg-bar"><i style="${side};background:${color}"></i></div>`
        + `<span class="wt-chg-val" style="color:${color}">${escapeHtml(text)}</span></div>`;
    }).join('');
  }

  // „01.01. – 05.11.2026 gegen 01.01. – 05.11.2025“
  function changesRange(c) {
    return `${rangeText(c.cur.start, c.cur.end)} ${t('gegen')} ${rangeText(c.vj.start, c.vj.end)}`;
  }

  // Der Zeitraum der Kenntage in einem Satz (ganze Jahre oder alle nur bis zum Kalendertag von heute).
  function kenntageRange(kt, ytd) {
    if (!ytd) return t('Ganze Kalenderjahre. Das laufende Jahr (*) zählt bis heute.');
    const date = fmtDate(formats.dm, Date.parse(kt.today + 'T12:00:00Z') / 1000);
    return t('Alle Jahre nur bis {date} gezählt, damit das laufende Jahr (*) vergleichbar ist.', {date});
  }

  // Der ganze Baustein der Karte: Satz zum Zeitraum darüber, die Felder darunter (ohne Schaltflächen).
  function energyKenntageBlock(kt, ytd) {
    return `<div class="kpi-sub">${escapeHtml(kenntageRange(kt, ytd))}</div>`
      + `<div class="wt-kt">${energyKenntage(kt, {ytd, years: 0, current: ZT.parts(Date.now() / 1000).year, interactive: false})}</div>`;
  }

  // Der ganze Baustein der Karte: Zeitraum darüber, die Zeilen darunter; ohne Verbraucher ein Hinweis.
  function energyChangesBlock(c) {
    if (!c.items.length) return `<div class="kpi-empty">${escapeHtml(t('Keine Veränderungen zum Vorjahr gefunden.'))}</div>`;
    return `<div class="kpi-sub">${escapeHtml(changesRange(c))}</div><div class="wt-chg">${energyChanges(c, {links: false})}</div>`;
  }

  window.ElementTableRender = {
    weatherComparison, WIND_KEYS, groupOf, inGroup,
    formats, fmtDate, rangeText, energy, columnName, delta, comparisonHead, cellHtml, energyComparison: renderTable,
    monthName, mean, present, monthKey, isPartialStart, monthStats, yearSum, energyMatrix,
    kenntagRule, kenntagLabels: KENNTAG_LABELS, energyKenntage, energyChanges, changesRange, kenntageRange, energyKenntageBlock, energyChangesBlock,
  };
})();
