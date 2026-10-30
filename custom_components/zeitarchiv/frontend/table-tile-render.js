// Tabellen der Dashboard-Kacheln als HTML, getrennt von der Kachel im DOM.
// Aus dashboard-tiles.js (renderTableTile) herausgelöst, damit dieselbe Tabelle ohne die Kachel-Hülle
// auch anderswo gebaut werden kann, etwa in einer Lovelace-Karte. buildHtml() bekommt die sichtbaren
// Spalten/Zeilen, den Stil und die berechneten Werte (compute() rechnet sie über TableCompute) und liefert den
// HTML-Text der Tabelle; afterInsert() setzt danach die gemessene Höhe der Gruppen-Kopfzeile.
// Braucht t(), escapeHtml und TableCompute (table-compute.js) als Globals.
(() => {
  // Ausgeblendete Spalten/Zeilen (Tabelleneditor, col.hidden/row.hidden) werden nicht gerendert, bleiben
  // aber Teil der Berechnung — dieselbe Regel wie in table_editor.html. computeValues() bekommt deshalb
  // ALLE Zeilen: sonst verschieben sich die Formel-Buchstaben, Formeln auf eine ausgeblendete Zeile
  // liefern "Fehler", und Summen-/Anteilszeilen weichen vom Editor ab. Erst danach werden die sichtbaren
  // Zeilen herausgezogen.
  function selectVisible(columns, rows) {
    const visibleCols = columns.filter(c => !c.hidden);
    const visibleRowIndexes = rows.map((r, i) => (r.hidden ? -1 : i)).filter(i => i >= 0);
    return {visibleCols, allRows: rows, visibleRowIndexes, visibleRows: visibleRowIndexes.map(i => rows[i])};
  }

  // Wählt das Sichtbare und berechnet die Werte (TableCompute.computeValues, Zeilensummen, Überlappung der
  // Spalten). Liefert alles, was buildHtml() braucht, oder {empty: true} ohne sichtbare Zeilen/Spalten, dann
  // wird nichts abgefragt. base/at: Adresse der App und Stichtag; queryTable: optional eine eigene Abfrage
  // (body → Antwort von /api/query-table), die Lovelace-Karte setzt hier die fertige Antwort des Servers ein.
  async function compute(columns, rows, {base = '', at = null, queryTable = null} = {}) {
    const selected = selectVisible(columns, rows);
    const {visibleCols, allRows, visibleRowIndexes, visibleRows} = selected;
    if (!visibleCols.length || !visibleRows.length) return {empty: true};
    const computed = await TableCompute.computeValues(base, visibleCols, allRows, {at, queryTable});
    const {windowStarts, windowEnds, isCurrent, elapsedSeconds, summable} = computed;
    const allValues = computed.values;
    // Σ-Spalte: nur die sichtbaren Spalten kommen hier an, ausgeblendete zählen also wie im Editor nie mit.
    const rowSums = TableCompute.computeRowSums(visibleCols, allRows, allValues, summable);
    const sumOverlapping = TableCompute.sumOverlap(visibleCols, windowStarts, windowEnds);
    const values = allValues.map(colValues => visibleRowIndexes.map(i => colValues[i]));
    return {
      visibleCols, allRows, visibleRowIndexes, visibleRows, values, allValues,
      windowStarts, windowEnds, isCurrent, elapsedSeconds, rowSums, sumOverlapping,
    };
  }

  function buildHtml({visibleCols, allRows, visibleRowIndexes, visibleRows, style, values, allValues, windowStarts, windowEnds, isCurrent, elapsedSeconds, rowSums, sumOverlapping}) {
    // Abschnitts-Mitglieder (Entität-/Gruppen-Zeilen zwischen zwei Trennlinien
    // derselben Spalte) — Traversal-Gegenstück zu sectionMemberCells() in
    // table_editor.html, hier index- statt uid-basiert (dieselbe Datenform
    // wie computeValues()). Läuft wie dort über ALLE Zeilen des Abschnitts,
    // auch ausgeblendete (allRows/allValues, ri ist der Index der sichtbaren
    // Zeile). Die eigentliche Anteilsrechnung bleibt in
    // TableCompute.percentOfTotalCell(), damit beide Seiten denselben
    // Rechenkern nutzen.
    function sectionMemberCells(ci, ri) {
      const idx = visibleRowIndexes[ri];
      let start = 0;
      for (let j = idx - 1; j >= 0; j--) { if (allRows[j].row_type === 'separator') { start = j + 1; break; } }
      let end = allRows.length;
      for (let j = idx + 1; j < allRows.length; j++) { if (allRows[j].row_type === 'separator') { end = j; break; } }
      const cells = [];
      for (let j = start; j < end; j++) {
        if (allRows[j].row_type !== 'entity' && allRows[j].row_type !== 'group') continue;
        cells.push(allValues[ci] && allValues[ci][j]);
      }
      return cells;
    }
    // Spaltenweise statt zeilenweise — dieselbe Umstellung wie
    // columnHeatmapRange() in table_editor.html (siehe Kommentar dort):
    // eine Zeile enthält hier oft sehr unterschiedliche Größenordnungen
    // (Tag vs. Jahr), der sinnvolle Vergleich ist zwischen mehreren Zeilen
    // DERSELBEN Spalte, nicht innerhalb einer Zeile über alle Spalten. Nur
    // Entität-/Gruppen-Zeilen zählen als Vergleichspartner — eine Summen-/
    // Formelzeile ist fast immer das Maximum ihres Abschnitts und würde die
    // Skala sonst allein durch ihre Natur verzerren.
    function columnHeatmapRange(ci, ri) {
      const idx = visibleRowIndexes[ri];
      let start = 0;
      for (let j = idx - 1; j >= 0; j--) { if (allRows[j].row_type === 'separator') { start = j + 1; break; } }
      let end = allRows.length;
      for (let j = idx + 1; j < allRows.length; j++) { if (allRows[j].row_type === 'separator') { end = j; break; } }
      const vals = [];
      for (let j = start; j < end; j++) {
        if (allRows[j].row_type !== 'entity' && allRows[j].row_type !== 'group') continue;
        const cell = allValues[ci] && allValues[ci][j];
        if (cell && !cell.error && cell.value != null) vals.push(cell.value);
      }
      if (!vals.length) return null;
      return {min: Math.min(...vals), max: Math.max(...vals)};
    }
    // row.hide_if_empty: keine Zeile im Slice-Limit "verschwenden", die am
    // Ende doch nicht gerendert wird — deshalb hier VOR dem Bauen geprüft,
    // nicht erst beim Rendern selbst übersprungen.
    function isRowEmpty(row, ri) {
      if (!row.hide_if_empty) return false;
      return visibleCols.every((c, ci) => {
        const cell = values[ci] && values[ci][ri];
        return !cell || cell.value == null || cell.value === 0;
      });
    }

    // Manuelle Spaltenbreite (col.width/style.label_col_width, in
    // table_editor.html per Ziehgriff gesetzt). min-width direkt auf th/td
    // reicht bei HTML-Tabellen NICHT: Der Auto-Layout-Algorithmus darf diese
    // Werte bei zu wenig Platz trotzdem neu verteilen. Sobald mindestens eine
    // gespeicherte Breite existiert, bekommt die Kachel deshalb zusätzlich
    // ein echtes <colgroup> und eine feste Tabellen-Mindestbreite aus der
    // Summe aller Spalten. Nicht manuell gesetzte Spalten erhalten nur in
    // diesem gemischten Layout einen vernünftigen Fallback; Tabellen ganz
    // ohne gespeicherte Breiten bleiben beim bisherigen Auto-Layout.
    const colWidthAttr = (w) => w ? ` style="width:${w}px;min-width:${w}px;max-width:${w}px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"` : '';
    const labelWidthAttr = colWidthAttr(style.label_col_width);

    const savedWidth = (w) => {
      const n = Number(w);
      return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
    };
    const savedLabelWidth = savedWidth(style.label_col_width);
    const savedValueWidths = visibleCols.map(c => savedWidth(c.width));
    // Nur gespeicherte WERT-Spaltenbreiten (oder "Spalten gleichmäßig")
    // erzwingen das feste <colgroup>-Layout unten — eine gespeicherte
    // Label-Spaltenbreite allein braucht das nicht: labelWidthAttr (s. u.)
    // setzt sie per Inline-Style direkt auf th/td, unabhängig vom
    // table-layout-Modus. Sonst zwang eine irgendwann mal per Ziehgriff
    // gesetzte Label-Breite ALLE Wertespalten unnötig auf die feste
    // 120px-Pauschalbreite (autoValueWidth) — sichtbar als deutlich zu
    // breite, nicht mehr auf die Kachel schrumpfende Tabelle.
    const hasSavedValueWidths = savedValueWidths.some(w => w != null);
    // "Spalten gleichmäßig" setzte bisher auf der Kachel zwingend width:100%
    // und war damit ein zweiter, unabhängiger Stauch-Pfad. Auch ohne alte
    // gespeicherte Einzelbreiten braucht diese Option deshalb das feste,
    // scrollbar breite Layout.
    const needsColumnLayout = hasSavedValueWidths || !!style.equal_value_cols;
    const longestRowLabel = visibleRows.reduce((n, row) => Math.max(n, String(row.label || '').length), 0);
    const autoLabelWidth = Math.max(120, Math.min(320, longestRowLabel * 8 + 24));
    // "Spalten gleichmäßig": alle Wertespalten gleich breit, bemessen an der
    // Spalte, deren Inhalt am meisten Platz braucht — nicht an einer festen
    // Pauschalbreite (die quetschte breitere Inhalte vorher mit ab). Dieselbe
    // Zeichen-basierte Heuristik wie autoLabelWidth oben, hier über den
    // tatsächlich formatierten Zellentext (Zahl + Einheit) jeder Spalte.
    const equalValueWidth = (() => {
      if (!style.equal_value_cols) return null;
      let longestCellText = 0;
      visibleCols.forEach((col, ci) => {
        longestCellText = Math.max(longestCellText, TableCompute.resolveLabel(col.label, windowStarts[ci]).length);
        visibleRows.forEach((row, ri) => {
          if (row.row_type === 'separator' || isRowEmpty(row, ri)) return;
          let cell = values[ci] && values[ci][ri];
          if (row.percent_of_total) cell = TableCompute.percentOfTotalCell(cell, sectionMemberCells(ci, ri));
          const decimals = row.percent_of_total ? '1' : col.decimals;
          const numberParts = TableCompute.cellNumberParts(cell, decimals, !!style.explicit_missing);
          const unit = style.show_units === false ? '' : TableCompute.cellUnit(cell);
          const text = `${numberParts.whole}${numberParts.separator}${numberParts.fraction}${unit ? ` ${unit}` : ''}`;
          longestCellText = Math.max(longestCellText, text.length);
        });
      });
      return Math.max(70, Math.min(260, longestCellText * 8 + 32));
    })();
    const autoValueWidth = equalValueWidth || 120;
    const showRowSum = !!style.show_row_sum;
    const sumLeft = showRowSum && style.row_sum_position !== 'right';
    const sumRight = showRowSum && !sumLeft;
    const sumLabel = (style.row_sum_label || '').trim() || 'Σ';
    // Bei "gleichmäßig" gilt equalValueWidth für JEDE Wertespalte, auch wenn
    // einzelne Spalten zusätzlich noch eine individuell gezogene Breite
    // gespeichert haben (table_editor.html) — sonst wären die Spalten trotz
    // aktivierter Option nicht wirklich alle gleich breit.
    const layoutWidths = needsColumnLayout
      ? [
          savedLabelWidth || autoLabelWidth,
          ...(sumLeft ? [autoValueWidth] : []),
          ...savedValueWidths.map(w => equalValueWidth || w || autoValueWidth),
          ...(sumRight ? [autoValueWidth] : []),
        ]
      : [];
    const savedTableWidth = layoutWidths.reduce((sum, width) => sum + width, 0);
    const tableWidthAttr = needsColumnLayout
      ? ` style="width:max(100%,${savedTableWidth}px);min-width:${savedTableWidth}px;table-layout:fixed;"`
      : '';
    const colgroup = needsColumnLayout
      ? `<colgroup>${layoutWidths.map(width => `<col style="width:${width}px">`).join('')}</colgroup>`
      : '';

    const sumHeadTh = () => {
      const overlapNote = t('Einige Spalten überschneiden sich zeitlich (z. B. Woche und Tag). Ihre Werte zählen in der Summe doppelt.');
      const tip = sumOverlapping ? ` data-tooltip-fixed="${escapeHtml(overlapNote)}"` : '';
      return `<th class="tbl-sum-col tbl-sum-head"${tip}>${escapeHtml(sumLabel)}${sumOverlapping ? '<span class="tbl-sum-warn" aria-hidden="true">!</span>' : ''}</th>`;
    };
    const sumTd = (row, ri) => {
      const cell = rowSums[visibleRowIndexes[ri]];
      const numberParts = TableCompute.cellNumberParts(cell, row.percent_of_total ? '1' : (visibleCols[0] ? (visibleCols.find(c => c.in_sum !== false) || visibleCols[0]).decimals : 'auto'), !!style.explicit_missing);
      const unit = style.show_units === false ? '' : TableCompute.cellUnit(cell);
      return `<td class="tbl-sum-col tbl-num${cell ? '' : ' tbl-sum-empty'}"><span class="tbl-cell"><span class="tbl-cell-number"><span class="tbl-number-whole">${escapeHtml(numberParts.whole)}</span><span class="tbl-number-separator">${escapeHtml(numberParts.separator)}</span><span class="tbl-number-fraction">${escapeHtml(numberParts.fraction)}</span></span>${unit ? `<span class="tbl-cell-unit">${escapeHtml(unit)}</span>` : ''}</span></td>`;
    };

    const styleClasses = TableCompute.styleClasses(style);
    let html = `<table class="dt compact dtile-mini-table ${styleClasses}"${tableWidthAttr}>${colgroup}<thead>`;
    // Mehrstufige Kopfzeile (col.group_label) — dieselbe Lauflängen-Logik wie
    // groupHeaderCells() in table_editor.html, hier direkt auf visibleCols
    // (die Kachel kürzt Spalten ohnehin schon aufs Sichtbare).
    if (visibleCols.some(c => (c.group_label || '').trim())) {
      html += `<tr class="tbl-header-row tbl-group-header-row"><th${labelWidthAttr}>&nbsp;</th>${sumLeft ? '<th></th>' : ''}`;
      let gi = 0;
      while (gi < visibleCols.length) {
        const label = (visibleCols[gi].group_label || '').trim();
        let span = 1;
        while (label && gi + span < visibleCols.length && (visibleCols[gi + span].group_label || '').trim() === label) span++;
        html += `<th colspan="${span}" class="tbl-group-header">${escapeHtml(label)}</th>`;
        gi += span;
      }
      html += `${sumRight ? '<th></th>' : ''}</tr>`;
    }
    html += `<tr class="tbl-header-row"><th${labelWidthAttr}>&nbsp;</th>${sumLeft ? sumHeadTh() : ''}`;
    // Beschriftungs-Platzhalter (z. B. "{jahr}") wurden beim Speichern bewusst
    // NICHT aufgelöst (siehe table_editor.html save()) — sonst würde eine so
    // beschriftete Spalte hier ewig denselben, beim Speichern eingefrorenen
    // Wert zeigen statt sich mit der Zeit automatisch zu aktualisieren.
    visibleCols.forEach((c, ci) => {
      const comparisonClass = TableCompute.isComparisonColumn(c) ? ' class="tbl-comparison-col"' : '';
      // Hinweis auf eine noch laufende (unvollständige) Woche/Monat/Jahr-
      // Spalte, dieselbe Kennzeichnung wie in table_editor.html —
      // data-tooltip-fixed (nicht das gewöhnliche data-tooltip), weil
      // .dtile-table-preview überläuft/scrollt und einen normalen
      // CSS-::after-Tooltip abschneiden würde (siehe fixed-tooltip.js).
      const periodNote = TableCompute.currentPeriodNote(c, isCurrent[ci], windowEnds[ci]);
      const periodTooltipAttr = periodNote ? ` data-tooltip-fixed="${escapeHtml(periodNote)}"` : '';
      const periodHint = periodNote ? '<span class="tbl-period-hint">i</span>' : '';
      html += `<th${comparisonClass}${colWidthAttr(c.width)}${periodTooltipAttr}>${escapeHtml(TableCompute.resolveLabel(c.label, windowStarts[ci]))}${periodHint}</th>`;
    });
    html += `${sumRight ? sumHeadTh() : ''}</tr></thead><tbody>`;
    let dataRowIndex = 0;
    visibleRows.forEach((row, ri) => {
      if (row.row_type === 'separator') {
        const span = visibleCols.length + 1 + (showRowSum ? 1 : 0);
        const sectionLabel = row.show_label && row.label ? escapeHtml(row.label) : '';
        const sepClasses = `tbl-separator-row${row.bold ? ' tbl-bold' : ''}`;
        html += `<tr class="${sepClasses}"><td colspan="${span}"><span class="tbl-separator-content"><span class="tbl-separator-line" aria-hidden="true"></span>${sectionLabel ? `<span class="tbl-separator-label">${sectionLabel}</span><span class="tbl-separator-line" aria-hidden="true"></span>` : ''}</span></td></tr>`;
        return;
      }
      if (isRowEmpty(row, ri)) return;
      const rowClasses = [];
      if (row.bold) rowClasses.push('tbl-bold');
      if (row.row_type === 'formula') rowClasses.push('tbl-formula-row');
      if (row.row_type === 'formula' && row.accent) rowClasses.push('tbl-row-accent');
      if (dataRowIndex % 2 === 1) rowClasses.push('tbl-zebra-alt');
      dataRowIndex += 1;
      html += `<tr${rowClasses.length ? ` class="${rowClasses.join(' ')}"` : ''}><td${labelWidthAttr}>${escapeHtml(row.label)}</td>${sumLeft ? sumTd(row, ri) : ''}`;
      visibleCols.forEach((col, ci) => {
        let cell = values[ci] && values[ci][ri];
        if (row.percent_of_total) cell = TableCompute.percentOfTotalCell(cell, sectionMemberCells(ci, ri));
        const cellClasses = ['tbl-num'];
        if (cell && cell.error) cellClasses.push('tbl-error');
        if (TableCompute.isComparisonColumn(col)) cellClasses.push('tbl-comparison-col');
        const decimals = row.percent_of_total ? '1' : col.decimals;
        const numberParts = TableCompute.cellNumberParts(cell, decimals, !!style.explicit_missing);
        const unit = style.show_units === false ? '' : TableCompute.cellUnit(cell);
        const comparisonIndex = TableCompute.comparisonIndexForBase(visibleCols, ci);
        const comparisonCell = comparisonIndex >= 0 ? (values[comparisonIndex] && values[comparisonIndex][ri]) : null;
        const deviation = style.show_deviation && !row.percent_of_total && comparisonIndex >= 0
          ? TableCompute.deviationText(cell, comparisonCell) : '';
        // Zusatzhinweis samt Vergleichswert, wenn die Prozentzahl auf
        // comparisonValue beruht (siehe deviationText()): die Zelle selbst
        // zeigt weiterhin den vollständigen Zeitraum, nur der Vergleich ist
        // auf "bisher vergangen" gekappt — ohne Erklärung UND Zahl wirkt das
        // wie ein Widerspruch zum vollen, daneben angezeigten Wert.
        const comparisonLabel = comparisonIndex >= 0
          ? TableCompute.resolveLabel(visibleCols[comparisonIndex].label, windowStarts[comparisonIndex]) : '';
        const comparisonValueStr = comparisonIndex >= 0
          ? TableCompute.comparisonValueText(comparisonCell, visibleCols[comparisonIndex].decimals) : '';
        const comparisonTimeStr = comparisonIndex >= 0
          ? TableCompute.comparisonElapsedTimeText(
              windowStarts[comparisonIndex], elapsedSeconds[comparisonIndex], visibleCols[comparisonIndex].range_key)
          : null;
        const deviationTitle = comparisonIndex < 0 ? '' : comparisonValueStr
          ? (comparisonTimeStr ? t('Gegenüber {label} bis {time}: {value}',{label: comparisonLabel, time: comparisonTimeStr, value: comparisonValueStr}) : t('Gegenüber {label}: {value}',{label: comparisonLabel, value: comparisonValueStr}))
          : t('Gegenüber {label}',{label: comparisonLabel});
        const widthCss = col.width ? `width:${col.width}px;max-width:${col.width}px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;` : '';
        const heatmapCss = (col.heatmap && (row.row_type === 'entity' || row.row_type === 'group'))
          ? TableCompute.heatmapStyle(values[ci] && values[ci][ri], columnHeatmapRange(ci, ri)) : '';
        const cellStyleAttr = (widthCss || heatmapCss) ? ` style="${widthCss}${heatmapCss}"` : '';
        html += `<td class="${cellClasses.join(' ')}"${cellStyleAttr}><span class="tbl-cell"><span class="tbl-cell-number"><span class="tbl-number-whole">${escapeHtml(numberParts.whole)}</span><span class="tbl-number-separator">${escapeHtml(numberParts.separator)}</span><span class="tbl-number-fraction">${escapeHtml(numberParts.fraction)}</span></span>${unit ? `<span class="tbl-cell-unit">${escapeHtml(unit)}</span>` : ''}</span>${deviation ? `<span class="tbl-cell-deviation" data-tooltip-fixed="${escapeHtml(deviationTitle)}">${escapeHtml(deviation)}</span>` : ''}</td>`;
      });
      html += `${sumRight ? sumTd(row, ri) : ''}</tr>`;
    });
    html += '</tbody></table>';
    return html;
  }

  // Nach dem Einsetzen der Tabelle: Höhe der Gruppen-Kopfzeile für "Header fixieren" bei zweistufigem
  // Kopf — dieselbe --tbl-group-header-h-Custom-Property wie in table_editor.html (siehe dortiger
  // Kommentar bei .tbl-style-sticky-header tr.tbl-header-row th: sticky auf thead/tr funktioniert in
  // Safari nicht, deshalb pro th einzeln mit gemessenem top-Versatz).
  function afterInsert(previewEl) {
    const tableEl = previewEl.querySelector('table');
    if (tableEl) {
      const groupRow = tableEl.querySelector('tr.tbl-group-header-row');
      const groupH = (groupRow && groupRow.offsetParent !== null) ? groupRow.getBoundingClientRect().height : 0;
      tableEl.style.setProperty('--tbl-group-header-h', groupH + 'px');
    }
  }

  window.TableTileRender = {selectVisible, compute, buildHtml, afterInsert};
})();
