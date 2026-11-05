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
  window.ElementTableRender = {formats, fmtDate, rangeText, energy, columnName, energyComparison: renderTable};
})();
