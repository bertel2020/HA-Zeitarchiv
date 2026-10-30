// Geteilte Rechenlogik für Vergleichstabellen (Konzept "Offene Punkte") —
// von table_editor.html (volle Bearbeitung) UND dashboard-tiles.js (kompakte
// Dashboard-Kachel) genutzt, damit beide garantiert dieselben Zahlen zeigen
// und ein Fix an einer Stelle nicht an der anderen vergessen wird. Reiner
// Berechnungscode, keine DOM-Abhängigkeit — arbeitet auf einfachen
// Columns-/Rows-Arrays (Index statt Alpine-uid), nicht auf dem reaktiven
// Zustand des Editors.
window.TableCompute = (() => {
  // Akzeptiertes Dezimaltrennzeichen für Zahl-Literale in Formeln, aus dem
  // zentralen Oberflächenformat abgeleitet (static/js/number-format.js) statt
  // hart auf "," verdrahtet — ein deutschsprachiger Nutzer tippt in einer
  // Formel-Konstante natürlicherweise Komma (z. B. "A * 3,5"), das bisher am
  // Parser scheiterte ("Unerwartetes Zeichen ','"). "." bleibt IMMER zusätzlich
  // gültig (unabhängig vom Trennzeichen der aktuellen Sprache), da Formeln als
  // Mini-Code gelesen werden, nicht als natürlichsprachige Zahl — keine
  // Tausendertrennung hier, das wäre in einer Formel ohnehin nicht sinnvoll.
  const FORMULA_DECIMAL_SEP = (window.NumberFormat && window.NumberFormat.DECIMAL_SEP) || ',';

  // Sicherer, kleiner Formel-Interpreter statt eval()/Function() — Formeln
  // stehen zwar nur in der eigenen Datenbank (kein Angriffsvektor von
  // außen), ein handgebauter Parser bleibt trotzdem die sauberere Wahl
  // gegenüber beliebigem Code-Eval für etwas so Einfaches wie "A / B * 100".
  // Unterstützt +, -, *, /, Klammern, Zeilen-Buchstaben (A-Z) und Zahlen.
  function evalFormula(expr, scope) {
    const s = (expr || '').replace(/\s+/g, '').toUpperCase();
    if (!s) throw new Error(t('Leere Formel'));
    let pos = 0;
    const peek = () => s[pos];
    function parseExpr() {
      let v = parseTerm();
      while (peek() === '+' || peek() === '-') {
        const op = s[pos++];
        const rhs = parseTerm();
        v = op === '+' ? v + rhs : v - rhs;
      }
      return v;
    }
    function parseTerm() {
      let v = parseFactor();
      while (peek() === '*' || peek() === '/') {
        const op = s[pos++];
        const rhs = parseFactor();
        v = op === '*' ? v * rhs : v / rhs;
      }
      return v;
    }
    function parseFactor() {
      if (peek() === '-') { pos++; return -parseFactor(); }
      if (peek() === '(') {
        pos++;
        const v = parseExpr();
        if (peek() !== ')') throw new Error(t('Schließende Klammer fehlt'));
        pos++;
        return v;
      }
      if (peek() && /[A-Z]/.test(peek())) {
        const letter = s[pos++];
        if (!(letter in scope)) throw new Error(t('Zeile {letter} ist hier nicht verfügbar', {letter}));
        const v = scope[letter];
        if (v == null) throw new Error(t('Zeile {letter} hat keinen Wert', {letter}));
        return v;
      }
      const start = pos;
      while (peek() && (/[0-9.]/.test(peek()) || peek() === FORMULA_DECIMAL_SEP)) pos++;
      if (pos === start) throw new Error(t('Unerwartetes Zeichen „{char}“',{char: peek() ?? ''}));
      const numText = s.slice(start, pos);
      const normalized = FORMULA_DECIMAL_SEP === '.' ? numText : numText.replace(FORMULA_DECIMAL_SEP, '.');
      // parseFloat() allein nähme nur den gültigen Anfang: "1.2.3" wäre 1,2,
      // "2..5" wäre 2 — ein Tippfehler ergäbe eine plausible, falsche Zahl.
      if (!/^(\d+\.?\d*|\.\d+)$/.test(normalized)) {
        throw new Error(t('Ungültige Zahl „{number}“', {number: numText}));
      }
      return parseFloat(normalized);
    }
    const result = parseExpr();
    if (pos < s.length) throw new Error(t('Unerwarteter Rest in der Formel'));
    // Division durch 0 (auch 0 / 0) ist kein Fehler in der Formel, sondern
    // eine Periode ohne Bezugsgröße (z. B. "km / Einheiten" in einem Monat
    // ohne Einheit) — deshalb kein Wert ("–") statt t("Fehler").
    if (!Number.isFinite(result)) return null;
    return result;
  }

  // Zentral in static/js/number-format.js (window.NumberFormat) — dieselbe
  // Formatierung wie überall sonst in der Oberfläche, siehe Kommentar dort.
  const fmtNum = (window.NumberFormat && window.NumberFormat.fmt) || (v => String(v));

  // decimals: der Spalten-eigene "Nachkommastellen"-String ("auto"/"0"/"1"/…,
  // dieselbe Konvention wie das entity-eigene Feld, siehe _TableColumnBody in
  // main.py) — rein optisch, fließt nirgends in eine Berechnung ein. Ohne
  // Angabe (ältere, vor dieser Funktion gespeicherte Tabellen) unverändert
  // NumberFormat.fmt()s Default (bis zu 4 signifikante Stellen).
  function cellValueText(cell, decimals, explicitMissing = false) {
    if (!cell) return explicitMissing ? t('Keine Daten') : '–';
    if (cell.error) return t('Fehler');
    if (cell.value == null) return explicitMissing ? t('Keine Daten') : '–';
    const decimalsInt = decimals && decimals !== 'auto' ? parseInt(decimals, 10) : null;
    return fmtNum(cell.value, decimalsInt);
  }

  function cellUnit(cell) {
    return cell && !cell.error && cell.value != null ? (cell.unit || '') : '';
  }

  function cellNumberParts(cell, decimals, explicitMissing = false) {
    const text = cellValueText(cell, decimals, explicitMissing);
    if (!cell || cell.error || cell.value == null) return {whole: text, separator: '', fraction: ''};
    const separator = (window.NumberFormat && window.NumberFormat.DECIMAL_SEP) || ',';
    const pos = text.lastIndexOf(separator);
    if (pos < 0) return {whole: text, separator: '', fraction: ''};
    return {whole: text.slice(0, pos), separator, fraction: text.slice(pos + separator.length)};
  }

  function cellText(cell, decimals, options = {}) {
    const value = cellValueText(cell, decimals, !!options.explicitMissing);
    const unit = options.showUnits === false ? '' : cellUnit(cell);
    return value + (unit ? ' ' + unit : '');
  }

  function isComparisonColumn(col) {
    return !!(col && ((col.offset || 0) < 0 || col.year_over_year));
  }

  // Formatiert den fairen, elapsed-gekappten Vergleichswert einer
  // Vergleichszelle (comparisonValue, siehe deviationText()) — für den
  // Tooltip der Prozentzahl, damit dort nicht nur "wogegen" (Spaltenname),
  // sondern auch "womit genau" verglichen wird sichtbar ist. Leerstring,
  // wenn kein fairer Vergleich vorliegt (Formel-/Summenzeilen, oder kein
  // same_elapsed angefordert) — dieselbe Bedingung wie in deviationText().
  function comparisonValueText(comparisonCell, decimals) {
    if (!comparisonCell || comparisonCell.comparisonValue == null) return '';
    return cellText({value: comparisonCell.comparisonValue, unit: comparisonCell.unit}, decimals);
  }

  // Zugehörige Vergleichsspalte für Tag/Monat/Jahr: gleicher Zeitraum,
  // aber mit Versatz oder Vorjahresmodus. Bewusst nur vorwärts suchen,
  // damit die Tabellenreihenfolge die visuelle Paarung bestimmt und die
  // Abweichung unter dem aktuellen statt unter dem historischen Wert steht.
  function comparisonIndexForBase(columns, baseIndex) {
    const base = columns[baseIndex];
    if (!base || isComparisonColumn(base)) return -1;
    for (let i = baseIndex + 1; i < columns.length; i++) {
      const candidate = columns[i];
      if (candidate.range_key === base.range_key && isComparisonColumn(candidate)) return i;
    }
    return -1;
  }

  function deviationText(baseCell, comparisonCell) {
    if (!baseCell || !comparisonCell || baseCell.error || comparisonCell.error ||
        baseCell.value == null || comparisonCell.value == null) return '';
    // comparisonValue (falls vorhanden): fairer, auf denselben Zeitabstand
    // gekappter Vergleichswert (same_elapsed, siehe memberComparisonValueFor()
    // unten) statt des vollen, immer angezeigten Zellwerts — sonst verglicht
    // z. B. "Tag bisher" unfair gegen den ganzen "Vortag" statt gegen "Vortag
    // bis zur selben Uhrzeit". null (Gruppen-/Formel-/Summenzeilen, oder wenn
    // der Server keinen same_elapsed-Vergleich geliefert hat): unverändert
    // der volle Wert wie bisher.
    const comparisonBase = comparisonCell.comparisonValue != null ? comparisonCell.comparisonValue : comparisonCell.value;
    if (comparisonBase === 0) return '';
    const percent = (baseCell.value - comparisonBase) / Math.abs(comparisonBase) * 100;
    if (!Number.isFinite(percent)) return '';
    const rounded = Math.abs(percent) >= 10 ? Math.round(percent) : Math.round(percent * 10) / 10;
    return `${rounded > 0 ? '+' : ''}${fmtNum(rounded, Number.isInteger(rounded) ? 0 : 1)} %`;
  }

  // row.percent_of_total: zeigt statt des absoluten Zellwerts den Anteil an
  // der Summe aller Entität-/Gruppen-Zeilen DERSELBEN Spalte im selben
  // Abschnitt (zwischen zwei Trennlinien bzw. Tabellenanfang/-ende) — anders
  // als bei der Summenzeile (nur Zeilen OBERHALB) hier bewusst der GANZE
  // Abschnitt, weil ein Anteil sich auf alle Geschwister-Zeilen bezieht, nicht
  // nur auf vorherige. memberCells kommt vorberechnet vom Aufrufer (uid- bzw.
  // index-basiert je nach Kontext, siehe sectionMemberCells() in
  // table_editor.html bzw. dashboard-tiles.js), damit dieser gemeinsame Kern
  // nicht selbst durchs rows-Array laufen muss.
  function percentOfTotalCell(cell, memberCells) {
    if (!cell || cell.error || cell.value == null) return cell;
    const total = memberCells.reduce((a, c) => a + (c && c.value != null ? c.value : 0), 0);
    if (!total) return {value: null, unit: '%'};
    return {value: (cell.value / total) * 100, unit: '%'};
  }

  // row.heatmap: Zellhintergrund nach Wert innerhalb der eigenen Zeile
  // (heller = niedrig, kräftiger = hoch) — range kommt vom Aufrufer
  // (Minimum/Maximum der sichtbaren Zellen DERSELBEN Zeile, siehe
  // rowHeatmapRange() in table_editor.html). --accent-bar (die zweite
  // Akzentfarbe, sonst für Balkendiagramme) statt --accent-line, damit eine
  // "heiße" Zelle nicht wie ein aktiver An/Aus-Chip (dort --accent-line)
  // aussieht. Deckelung bei 60%, damit der Zahlentext bei einem Maximalwert
  // noch lesbar bleibt.
  function heatmapStyle(cell, range) {
    if (!cell || cell.error || cell.value == null || !range || range.max === range.min) return '';
    const t = (cell.value - range.min) / (range.max - range.min);
    const pct = Math.round(Math.max(0, Math.min(1, t)) * 60);
    return `background:color-mix(in srgb, var(--accent-bar) ${pct}%, var(--surface));`;
  }

  // Buchstaben-Kürzel je Datenzeile (A, B, C, … Z, dann wieder von vorn) —
  // Trennlinien sind rein optisch und verbrauchen deshalb bewusst keinen
  // Buchstaben. Dieselbe Zuordnung wie rowLetters in table_editor.html, hier
  // als reine Funktion über ein rows-Array statt eines Alpine-Getters.
  function rowLetters(rows) {
    let dataIndex = 0;
    return rows.map(r => {
      if (r.row_type === 'separator') return null;
      return String.fromCharCode(65 + ((dataIndex++) % 26));
    });
  }

  // Leere Formel-Einheit = automatische Übernahme von der ersten in der
  // Formel referenzierten Zeile, die eine Einheit besitzt. Dimensionslose
  // oder umgerechnete Ergebnisse können im Editor explizit überschrieben
  // werden (z. B. "%" für A / B * 100).
  function inheritedFormulaUnit(expr, unitScope) {
    const references = (expr || '').toUpperCase().match(/[A-Z]/g) || [];
    for (const letter of references) {
      if (unitScope[letter]) return unitScope[letter];
    }
    return '';
  }

  // Aggregiert die Buckets EINER Entität innerhalb einer Spalte (Zeitraum) zu
  // einem Zahlenwert, je nach gewählter Zeilen-Aggregation. "auto" ist das
  // historische Verhalten (Zähler/Schalter -> Summe, sonst Durchschnitt der
  // Bucket-Werte) und bleibt für bestehende Tabellen unverändert. min/max
  // nutzen das echte Bucket-Minimum/-Maximum (server-seitig aus den
  // Rohwerten berechnet, siehe storage/query.py `min_value`/`max_value`),
  // NICHT das Minimum/Maximum der Bucket-DURCHSCHNITTE — sonst würde z. B.
  // eine kurze Temperaturspitze innerhalb eines Stunden-Buckets im
  // Tages-/Monats-Maximum verschwinden. Kein Datenpunkt im Zeitraum: bei
  // avg/sum/auto weiterhin 0 (bisheriges Verhalten, wichtig für Gruppen-
  // Summen aus mehreren Mitgliedern), bei min/max stattdessen null — 0 wäre
  // dort kein neutrales Element, sondern ein plausibler, aber falscher Wert.
  function memberValueFor(series, aggregation) {
    // Der Tabellen-Batch-Endpunkt verdichtet die Chart-Punkte bereits auf
    // genau diese fünf Werte. Der points-Fallback hält den Rechenkern zugleich
    // mit älteren/anderen Aufrufern kompatibel.
    if (series.aggregates && Object.prototype.hasOwnProperty.call(series.aggregates, aggregation)) {
      return series.aggregates[aggregation];
    }
    const pts = series.points || [];
    if (aggregation === 'min' || aggregation === 'max') {
      if (!pts.length) return null;
      const key = aggregation === 'min' ? 'min' : 'max';
      const vals = pts.map(p => (p[key] != null ? p[key] : p.value)).filter(v => v != null);
      return vals.length ? Math[aggregation](...vals) : null;
    }
    if (!pts.length) return 0;
    const total = pts.reduce((a, p) => a + (p.value || 0), 0);
    if (aggregation === 'sum') return total;
    if (aggregation === 'avg') return total / pts.length;
    const isSum = series.aggregation_type === 'counter' || series.aggregation_type === 'switch';
    return isSum ? total : total / pts.length;
  }

  // Fairer Vergleichswert für eine same_elapsed-Spalte (Vortag/Vorwoche/…
  // neben Tag/Woche/…, siehe deviationText()) — server-seitig auf denselben
  // Zeitabstand vom Periodenanfang gekappt wie die noch laufende aktuelle
  // Periode (comparison_aggregates, siehe _table_comparison_aggregates() in
  // api_routes.py). null, wenn der Server keinen same_elapsed-Vergleich
  // geliefert hat — deviationText() fällt dann auf den vollen Wert zurück.
  function memberComparisonValueFor(series, aggregation) {
    if (series.comparison_aggregates
        && Object.prototype.hasOwnProperty.call(series.comparison_aggregates, aggregation)) {
      return series.comparison_aggregates[aggregation];
    }
    return null;
  }

  // Der Körper der Abfrage an /api/query-table: alle gebrauchten Entitäten und je Spalte Zeitraum,
  // Versatz und Vergleichsart. Rein, damit der Server (card_routes.table_query_body) dieselbe Abfrage
  // stellen kann; ein Test hält beide gleich. Ohne Entität-/Gruppen-Zeile gibt es nichts zu fragen (null).
  function queryBody(columns, rows, at = null) {
    const entityRows = rows.filter(r => r.row_type === 'entity' || r.row_type === 'group');
    const entityIds = [...new Set(entityRows.flatMap(r => r.entity_ids))];
    if (!entityIds.length) return null;
    return {
      entity_ids: entityIds,
      at,
      columns: columns.map(col => ({
        range_key: col.range_key,
        offset: col.offset || 0,
        year_over_year: !!col.year_over_year,
        // "Gleicher Zeitpunkt"-Vergleich: eine Vergleichsspalte (Versatz<0)
        // wird auf denselben Abstand vom Periodenanfang gekappt wie die
        // noch laufende aktuelle Periode — aber NUR, wenn diese Tabelle
        // überhaupt eine laufende Basis-Spalte (Versatz 0, kein
        // Vorjahresvergleich) mit demselben Zeitraum-Typ enthält. Ohne
        // Basis-Spalte bleibt die Vergleichsspalte unverändert vollständig
        // (z. B. eine reine "Vormonat"-Spalte ohne "Monat" daneben).
        same_elapsed: !at && (col.offset || 0) < 0 && !col.year_over_year
          && columns.some(c => c.range_key === col.range_key && (c.offset || 0) === 0 && !c.year_over_year),
      })),
    };
  }

  // Die Abfrage der Oberfläche; die Lovelace-Karte reicht stattdessen die fertige Antwort des Servers.
  const defaultQueryTable = (base) => async (body) => {
    const res = await fetch(`${base}/api/query-table`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(t('Tabellenabfrage fehlgeschlagen ({status})',{status: res.status}));
    return res.json();
  };

  // Berechnet values[colIndex][rowIndex] = {value, unit} | {error:true} | null
  // — ein gemeinsamer Request an /api/query-table für alle Spalten und
  // gebrauchten Entitäten, Formel-Zeilen danach in Zeilen-
  // Reihenfolge ausgewertet (Verkettung: eine Formel darf eine bereits
  // berechnete FRÜHERE Formel-Zeile referenzieren). windowStarts[colIndex]
  // ist der von derselben Anfrage mitgelieferte, tatsächlich aufgelöste
  // Fensterbeginn (Sekunden, siehe query.py `window_start`) — Grundlage für
  // die Beschriftungs-Platzhalter ({jahr}, {monat}, …, siehe resolveLabel()
  // unten). Bleibt null, solange die Spalte keine Entität/Gruppen-Zeile
  // referenziert (kein Request nötig) — resolveLabel() liefert dann
  // unverändert die rohe Beschriftung zurück.
  // at: Stichtag der Zeitraum-Navigation eines Dashboards (JJJJ-MM-TT, nur
  // dashboard-tiles.js) — der Server verschiebt damit jede Spalte auf die
  // Periode, die diesen Tag enthält. Eine solche Periode läuft nicht mehr,
  // deshalb dann auch kein "Gleicher Zeitpunkt"-Vergleich.
  // queryTable: optional eine eigene Abfrage (body → Antwort von /api/query-table), statt sie über fetch zu stellen.
  async function computeValues(base, columns, rows, {at = null, queryTable = null} = {}) {
    const letters = rowLetters(rows);
    const entityRows = rows.filter(r => r.row_type === 'entity' || r.row_type === 'group');
    const allEntityIds = [...new Set(entityRows.flatMap(r => r.entity_ids))];
    const values = columns.map(() => new Array(rows.length).fill(null));
    const windowStarts = columns.map(() => null);
    // Tatsächlich aufgelöstes (ggf. auf "jetzt" gedecktes) Fensterende, siehe
    // window_end in query_series()/api_routes.py — Grundlage für
    // currentPeriodNote() unten (Enddatum einer noch laufenden Spalte).
    const windowEnds = columns.map(() => null);
    // offset === 0 (siehe is_current in query_series()) — bei einer
    // Vorjahresvergleichs-Spalte (year_over_year) bezieht sich das auf deren
    // EIGENEN offset vor der Jahresverschiebung, nicht auf das verschobene
    // Zieljahr: eine year_over_year-Spalte mit offset 0 ist also ebenfalls
    // "aktuell" in diesem Sinn, weil ihr Fenster aus demselben, gerade erst
    // gedeckelten Basis-Fenster gebaut ist (siehe currentPeriodNote()).
    const isCurrent = columns.map(() => false);
    // Sekunden seit windowStarts[colIndex], auf die ein same_elapsed-Vergleich
    // gekappt wurde (siehe elapsed_seconds in query_series()/api_routes.py) —
    // Grundlage für comparisonElapsedTimeText() unten (Uhrzeit-Anzeige im
    // Abweichungs-Tooltip). null, wenn die Spalte ungekappt ist.
    const elapsedSeconds = columns.map(() => null);
    // Je Entität-/Gruppen-Zeile: darf eine Σ-Spalte die Spaltenwerte
    // aufsummieren? (siehe computeRowSums()). Nach der Server-Antwort gesetzt.
    const summable = rows.map(() => false);

    let columnData = [];
    if (allEntityIds.length) {
      try {
        columnData = (await (queryTable || defaultQueryTable(base))(queryBody(columns, rows, at))).columns || [];
      } catch (e) {
        columnData = [];
      }
    }

    columns.forEach((col, ci) => {
      const data = columnData[ci] || {series: []};
      windowStarts[ci] = data.window_start ?? null;
      windowEnds[ci] = data.window_end ?? null;
      isCurrent[ci] = !!data.is_current;
      elapsedSeconds[ci] = data.elapsed_seconds ?? null;
      const byEntity = {};
      (data.series || []).forEach(s => { byEntity[s.entity_id] = s; });
      rows.forEach((row, ri) => {
        if (row.row_type === 'formula' || row.row_type === 'separator' || row.row_type === 'summary') return;
        const members = row.entity_ids.map(id => byEntity[id]).filter(Boolean);
        if (!members.length) { values[ci][ri] = null; return; }
        const aggregation = row.aggregation || 'auto';
        // Summierbar: ausdrücklich "Σ Summe", oder "Automatisch" bei lauter
        // Zählern/Schaltern. Ø/Min/Max und Zustände sind es nie — selbst ein
        // Zähler mit Zeilen-Aggregation "max" darf nicht addiert werden.
        summable[ri] = row.entity_ids.length === members.length && (aggregation === 'sum'
          || (aggregation === 'auto' && members.every(s => s.aggregation_type === 'counter' || s.aggregation_type === 'switch')));
        const memberValues = members.map(s => memberValueFor(s, aggregation));
        const memberComparisonValues = members.map(s => memberComparisonValueFor(s, aggregation));
        let value;
        let comparisonValue;
        if (aggregation === 'min' || aggregation === 'max') {
          // Ein Mitglied ganz ohne Datenpunkte fließt hier NICHT als 0 ein
          // (anders als bei avg/sum/auto unten) — sonst würde eine Entität
          // ohne Daten im Zeitraum fälschlich zum globalen Minimum. Sind ALLE
          // Mitglieder ohne Daten, bleibt die Zelle leer statt 0.
          const valid = memberValues.filter(v => v != null);
          if (!valid.length) { values[ci][ri] = null; return; }
          value = aggregation === 'min' ? Math.min(...valid) : Math.max(...valid);
          const validComparison = memberComparisonValues.filter(v => v != null);
          comparisonValue = validComparison.length
            ? (aggregation === 'min' ? Math.min(...validComparison) : Math.max(...validComparison))
            : null;
        } else {
          // Wie bisher: eine Gruppen-Zeile summiert die (je nach Modus schon
          // aggregierten) Mitglieder-Werte zusätzlich noch einmal auf.
          value = memberValues.reduce((a, v) => a + (v || 0), 0);
          comparisonValue = memberComparisonValues.every(v => v == null)
            ? null
            : memberComparisonValues.reduce((a, v) => a + (v || 0), 0);
        }
        const memberUnits = [...new Set(members.map(member => member.unit || ''))];
        values[ci][ri] = {value, unit: memberUnits.length === 1 ? memberUnits[0] : '', comparisonValue};
      });
    });

    columns.forEach((col, ci) => {
      rows.forEach((row, ri) => {
        if (row.row_type === 'formula') {
          const scope = {};
          const unitScope = {};
          for (let j = 0; j < ri; j++) {
            if (!letters[j]) continue;
            const cell = values[ci][j];
            scope[letters[j]] = cell ? cell.value : null;
            unitScope[letters[j]] = cell ? (cell.unit || '') : '';
          }
          const unit = (row.formula_unit || '').trim() || inheritedFormulaUnit(row.formula, unitScope);
          try {
            values[ci][ri] = {value: evalFormula(row.formula, scope), unit};
          } catch (e) {
            values[ci][ri] = {value: null, unit, error: true};
          }
        } else if (row.row_type === 'summary') {
          // Summe/Durchschnitt aller Entität-/Gruppen-Zeilen SEIT DER LETZTEN
          // TRENNLINIE (nicht ab Tabellenanfang) — dieselbe Abschnitts-Logik
          // wie sectionMemberCells() in table_editor.html, hier nur über den
          // Index statt uid. Absichtlich ohne Formel-/andere Summenzeilen,
          // sonst würde ein bereits aufsummierter Wert doppelt gezählt.
          // Steht die Summenzeile direkt UNTER einer Trennlinie (Abschnitt ohne
          // eigene Entität-/Gruppen-Zeile), ist sie eine Ergebniszeile für den
          // Abschnitt darüber — sonst bliebe sie leer.
          let sectionEnd = ri;
          let memberCells = [];
          while (true) {
            let sectionStart = 0;
            for (let j = sectionEnd - 1; j >= 0; j--) {
              if (rows[j].row_type === 'separator') { sectionStart = j + 1; break; }
            }
            const hasMembers = rows.slice(sectionStart, sectionEnd)
              .some(r => r.row_type === 'entity' || r.row_type === 'group');
            if (!hasMembers && sectionStart > 0) { sectionEnd = sectionStart - 1; continue; }
            for (let j = sectionStart; j < sectionEnd; j++) {
              if (rows[j].row_type !== 'entity' && rows[j].row_type !== 'group') continue;
              const cell = values[ci][j];
              if (cell && cell.value != null) memberCells.push(cell);
            }
            break;
          }
          if (!memberCells.length) { values[ci][ri] = null; return; }
          const total = memberCells.reduce((a, c) => a + c.value, 0);
          const value = row.aggregation === 'avg' ? total / memberCells.length : total;
          const units = [...new Set(memberCells.map(c => c.unit || ''))];
          values[ci][ri] = {value, unit: units.length === 1 ? units[0] : ''};
        }
      });
    });

    return {values, windowStarts, windowEnds, isCurrent, elapsedSeconds, summable};
  }

  // Σ-Spalte: je Zeile die Summe über die einbezogenen Spalten (nicht
  // ausgeblendet, col.in_sum !== false). Ein Ergebnis je Zeile, im Format von
  // values[ci][ri]; null = keine Summe ("–"). Läuft in Zeilenreihenfolge wie
  // computeValues(), damit Formeln auf bereits berechnete Σ-Werte zugreifen.
  // - Entität/Gruppe: Summe der Spaltenwerte, nur wenn summable[ri] (Zähler/
  //   Schalter bzw. Aggregation "Σ Summe"), sonst null.
  // - Formel: dieselbe Formel noch einmal auf den Σ-Werten ihrer Zeilen —
  //   bei A/B*100 ergibt das ΣA/ΣB statt einer Summe von Quotienten. Ist eine
  //   referenzierte Zeile null, ist es die Formel auch.
  // - Summenzeile: Summe (bzw. Ø) der Σ ihrer Abschnitts-Mitglieder, null,
  //   sobald eines davon null ist (eine Teilsumme sähe vollständig aus).
  // - % Anteil: Σ der Zeile im Verhältnis zur Σ des ganzen Abschnitts.
  function computeRowSums(columns, rows, values, summable) {
    const included = columns.map((c, ci) => ci).filter(ci => !columns[ci].hidden && columns[ci].in_sum !== false);
    const letters = rowLetters(rows);
    const raw = rows.map(() => null);
    const isMember = r => r.row_type === 'entity' || r.row_type === 'group';
    const sectionOf = (ri) => {
      // Dieselbe Abschnitts-Suche wie bei der Summenzeile in computeValues().
      let sectionEnd = ri;
      while (true) {
        let sectionStart = 0;
        for (let j = sectionEnd - 1; j >= 0; j--) {
          if (rows[j].row_type === 'separator') { sectionStart = j + 1; break; }
        }
        const hasMembers = rows.slice(sectionStart, sectionEnd).some(isMember);
        if (!hasMembers && sectionStart > 0) { sectionEnd = sectionStart - 1; continue; }
        return {start: sectionStart, end: sectionEnd};
      }
    };
    rows.forEach((row, ri) => {
      if (isMember(row)) {
        if (!summable || !summable[ri]) return;
        const cells = included.map(ci => values[ci][ri]).filter(c => c && !c.error && c.value != null);
        if (!cells.length) return;
        const units = [...new Set(cells.map(c => c.unit || ''))];
        raw[ri] = {value: cells.reduce((a, c) => a + c.value, 0), unit: units.length === 1 ? units[0] : ''};
      } else if (row.row_type === 'formula') {
        if (!included.length) return;
        const refs = [...new Set((row.formula || '').toUpperCase().match(/[A-Z]/g) || [])];
        const scope = {};
        const unitScope = {};
        for (let j = 0; j < ri; j++) {
          if (!letters[j]) continue;
          scope[letters[j]] = raw[j] ? raw[j].value : null;
          unitScope[letters[j]] = raw[j] ? (raw[j].unit || '') : '';
        }
        if (refs.some(l => l in scope && scope[l] == null)) return;
        const unit = (row.formula_unit || '').trim() || inheritedFormulaUnit(row.formula, unitScope);
        try {
          const value = evalFormula(row.formula, scope);
          raw[ri] = value == null ? null : {value, unit};
        } catch (e) {
          raw[ri] = null;
        }
      } else if (row.row_type === 'summary') {
        const {start, end} = sectionOf(ri);
        const members = [];
        for (let j = start; j < end; j++) if (isMember(rows[j])) members.push(raw[j]);
        if (!members.length || members.some(m => m == null)) return;
        const total = members.reduce((a, m) => a + m.value, 0);
        const units = [...new Set(members.map(m => m.unit || ''))];
        raw[ri] = {value: row.aggregation === 'avg' ? total / members.length : total, unit: units.length === 1 ? units[0] : ''};
      }
    });
    return rows.map((row, ri) => {
      if (!raw[ri] || !row.percent_of_total || !isMember(row)) return raw[ri];
      // Eigener Abschnitt der Zeile (anders als bei der Summenzeile keine
      // Rückwärtssuche über Trennlinien hinweg).
      let start = 0;
      for (let j = ri - 1; j >= 0; j--) { if (rows[j].row_type === 'separator') { start = j + 1; break; } }
      const cells = [];
      for (let j = start; j < rows.length && rows[j].row_type !== 'separator'; j++) if (isMember(rows[j])) cells.push(raw[j]);
      return percentOfTotalCell(raw[ri], cells);
    });
  }

  // Warnung für die Kopfzelle: überschneiden sich zwei einbezogene Spalten
  // zeitlich (z. B. "Woche" und "Tag"), zählt Σ Werte doppelt.
  function sumOverlap(columns, windowStarts, windowEnds) {
    const spans = [];
    columns.forEach((col, ci) => {
      if (col.hidden || col.in_sum === false) return;
      if (windowStarts[ci] == null || windowEnds[ci] == null) return;
      spans.push([windowStarts[ci], windowEnds[ci]]);
    });
    spans.sort((a, b) => a[0] - b[0]);
    for (let i = 1; i < spans.length; i++) if (spans[i][0] < spans[i - 1][1]) return true;
    return false;
  }

  // Datum/Uhrzeit in der Zeitzone des Servers (static/js/server-time.js), nicht
  // des Browsers — sonst zeigt ein Browser hinter der Serverzone den Vortag.
  const zoned = (options) => window.ServerTime.withZone(options);

  // Uhrzeit-Text für den fairen Vergleichswert einer same_elapsed-Spalte
  // (z. B. "bis 12:16 Uhr", siehe elapsed_seconds oben) — der tatsächliche
  // Bezugszeitpunkt ist windowStart + elapsedSeconds derselben Spalte. null,
  // wenn die Spalte keinen elapsed-Wert hat (kein same_elapsed-Vergleich).
  // Bei Stunde/Tag identifiziert die Uhrzeit allein den Cutoff bereits
  // eindeutig (derselbe Kalendertag wie die Basis-Spalte). Bei Woche/Monat/
  // Jahr liegt der Cutoff dagegen auf einem ANDEREN Tag als der Perioden-
  // anfang — "bis 18:43 Uhr" allein sagt dann nicht, welcher Tag im Vormonat/
  // Vorjahr gemeint ist, deshalb zusätzlich das Datum davor.
  function comparisonElapsedTimeText(windowStart, elapsedSeconds, rangeKey) {
    if (windowStart == null || elapsedSeconds == null) return null;
    const cutoff = new Date((windowStart + elapsedSeconds) * 1000);
    const timeText = t('{range} Uhr', {range: cutoff.toLocaleTimeString(window.ZA_FORMAT, zoned({hour: '2-digit', minute: '2-digit'}))});
    if (rangeKey === 'hour' || rangeKey === 'day') return timeText;
    const dateText = cutoff.toLocaleDateString(window.ZA_FORMAT, zoned({day: '2-digit', month: '2-digit'}));
    return `${dateText}, ${timeText}`;
  }

  // Kurzform "TT.MM." (bewusst ohne Jahr — die Spaltenbeschriftung nennt das
  // Jahr bereits) für den Cutoff einer noch laufenden Woche/Monat/Jahr-
  // Spalte, siehe shortCutoffText()/currentPeriodNote() unten.
  function shortDateText(epochSeconds) {
    if (epochSeconds == null) return null;
    return new Date(epochSeconds * 1000).toLocaleDateString(window.ZA_FORMAT, zoned({day: '2-digit', month: '2-digit'}));
  }

  // "HH:MM Uhr" für eine noch laufende Stunde/Tag-Spalte — ein Datum wäre
  // dort doppelt gemoppelt (die Beschriftung selbst nennt schon den Tag,
  // z. B. bei einer Vorjahresvergleichs-Spalte "21.09.25") und sagt zudem
  // nicht, WIE weit der Tag/die Stunde bereits gelaufen ist.
  function shortTimeText(epochSeconds) {
    if (epochSeconds == null) return null;
    return t('{range} Uhr', {range: new Date(epochSeconds * 1000).toLocaleTimeString(window.ZA_FORMAT, zoned({hour: '2-digit', minute: '2-digit'}))});
  }

  // Cutoff-Text passend zum Zeitraumtyp — Uhrzeit bei Stunde/Tag, sonst
  // Datum (siehe shortDateText()/shortTimeText() oben).
  function shortCutoffText(rangeKey, epochSeconds) {
    return (rangeKey === 'hour' || rangeKey === 'day')
      ? shortTimeText(epochSeconds)
      : shortDateText(epochSeconds);
  }

  // Ausgeschriebene Zeitraum-Phrase für eine noch laufende BASIS-Spalte
  // (kein Vorjahresvergleich) — dieselbe Wortwahl wie TILE_RANGE_WINDOW in
  // dashboard-tiles.js (eigene, unabhängige Kopie: andere Stelle, gleiche
  // Formulierung fürs Wiedererkennen). Stunde/Tag fehlen absichtlich: deren
  // eigenes Datum identifiziert den Zeitraum bereits eindeutig, "im
  // laufenden Tag" wäre nur Rauschen.
  const CURRENT_PERIOD_PHRASE = {
    week: t('in der laufenden Kalenderwoche'), month: t('im laufenden Monat'), year: t('im laufenden Jahr'),
  };

  // Erklärender Hinweis für eine Spalte, deren Wert (noch) nicht den ganzen
  // Zeitraum abdeckt — weder an der Kopfzeile noch im CSV-Export sonst
  // irgendwo erkennbar (siehe Konzept "laufendes Jahr"):
  // * Basis-Spalte (offset 0, kein Vorjahresvergleich): zeigt die noch
  //   laufende, nicht abgeschlossene Periode — Text nennt Zeitraumart UND
  //   Enddatum ("im laufenden Jahr · bis 21.09."). Nur Woche/Monat/Jahr
  //   (siehe CURRENT_PERIOD_PHRASE), Stunde/Tag bekommen hier nie einen
  //   Hinweis.
  // * Vorjahresvergleichs-Spalte (year_over_year): ihr Fenster ist aus
  //   genau demselben, bereits gedeckelten Basis-Fenster gebaut, nur um ein
  //   Jahr verschoben (siehe query.py `_window()`/year_over_year) — fair
  //   für den Vergleich, aber ebenso keine vollständige Periode. Die eigene
  //   Beschriftung sagt bereits "Vorjahr" o. ä. bzw. bei Stunde/Tag das
  //   Datum selbst — hier nur der Cutoff (Uhrzeit bei Stunde/Tag, sonst
  //   Datum, siehe shortCutoffText()).
  // null, wenn nichts davon zutrifft: eine abgeschlossene Vor-Spalte
  // (offset < 0 ohne year_over_year) zeigt immer den vollständigen
  // Zeitraum (siehe _cap() in query.py) und braucht keinen Hinweis.
  function currentPeriodNote(col, isCurrentCol, windowEnd) {
    if (!isCurrentCol) return null;
    const cutoff = shortCutoffText(col.range_key, windowEnd);
    if (!cutoff) return null;
    if (col.year_over_year) return t('bis {cutoff}', {cutoff});
    const phrase = CURRENT_PERIOD_PHRASE[col.range_key];
    return phrase ? t('{phrase} · bis {cutoff}', {phrase, cutoff}) : null;
  }

  // Dieselbe Bedingung wie currentPeriodNote() (über deren Rückgabe geprüft,
  // statt sie zu duplizieren), als knapper Klartext-Zusatz für Stellen ohne
  // Hover (CSV-Export) statt des ausgeschriebenen Tooltips.
  function currentPeriodShortSuffix(col, isCurrentCol, windowEnd) {
    if (!currentPeriodNote(col, isCurrentCol, windowEnd)) return '';
    return ' ' + t('(bis {cutoff})', {cutoff: shortCutoffText(col.range_key, windowEnd)});
  }

  // Monatsnamen/-kürzel für resolveLabel() unten — dieselbe Wortwahl wie der
  // Rest der Oberfläche (z. B. previousYearPeriodLabel in entity_detail.html),
  // hier nur als Kalender-Vokabular statt Zeitraum-Namen.
  const MONTH_NAMES = [t('Januar'), t('Februar'), t('März'), t('April'), t('Mai'), t('Juni'), t('Juli'), t('August'), t('September'), t('Oktober'), t('November'), t('Dezember')];
  const WEEKDAY_NAMES = [t('Sonntag'), t('Montag'), t('Dienstag'), t('Mittwoch'), t('Donnerstag'), t('Freitag'), t('Samstag')];
  const WEEKDAY_NAMES_SHORT = [t('So'), t('Mo'), t('Di'), t('Mi'), t('Do'), t('Fr'), t('Sa')];
  const MONTH_NAMES_SHORT = [t('Jan'), t('Feb'), t('Mär'), t('Apr'), t('Mai'), t('Jun'), t('Jul'), t('Aug'), t('Sep'), t('Okt'), t('Nov'), t('Dez')];

  // ISO-8601-Kalenderwoche (Woche 1 = die Woche mit dem ersten Donnerstag des
  // Jahres) — Standardalgorithmus über den nächsten Donnerstag derselben
  // Woche, damit Jahreswechsel innerhalb einer Woche (z. B. 30./31. Dezember)
  // korrekt der Woche des jeweils überwiegenden Jahres zugeordnet werden.
  function isoWeekNumber(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - dayNum + 3);
    const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
    const diff = d - firstThursday;
    return 1 + Math.round(diff / (7 * 24 * 3600 * 1000));
  }

  // Bekannte Platzhalter für Spalten-Beschriftungen — siehe LABEL_VARIABLES
  // unten (Einfügehilfe im Editor) für die Anzeige-Beschriftung je Token.
  // Nur diese Namen werden ersetzt; ein Tippfehler wie "{jhar}" matcht das
  // Muster nicht und bleibt deshalb sichtbar im Text stehen, statt
  // kommentarlos zu verschwinden.
  // Zu jedem deutschen Namen gibt es einen englischen Alias; gespeichert wird,
  // was im Feld steht, beide Schreibweisen funktionieren in jeder Sprache. Die
  // deutschen Namen bleiben gültig, weil sie in bestehenden Tabellen stehen.
  const LABEL_TOKEN_ALIASES = {
    year: 'jahr', year_short: 'jahr_kurz', quarter: 'quartal', month: 'monat',
    month_short: 'monat_kurz', month_no: 'monat_nr', week: 'woche', day: 'tag', weekday: 'wochentag', weekday_short: 'wochentag_kurz', decade: 'dekade',
  };
  const LABEL_TOKEN_PATTERN = new RegExp(
    '\\{(' + [...Object.keys(LABEL_TOKEN_ALIASES), ...Object.values(LABEL_TOKEN_ALIASES)].join('|') + ')\\}', 'g');

  // Ersetzt Platzhalter in einer Spalten-Beschriftung durch Kalenderwerte des
  // TATSÄCHLICH aufgelösten Zeitraums dieser Spalte (windowStartEpoch, aus
  // computeValues() oben) — nicht des heutigen Datums. Eine Spalte "Jahr,
  // Versatz -1" mit Beschriftung "{jahr}" zeigt dadurch automatisch das
  // Vorjahr, nächstes Jahr automatisch das dann aktuelle Vorjahr, ganz ohne
  // manuelles Nachpflegen. Labels ohne "{" sowie windowStartEpoch == null
  // (z. B. bevor computeValues() das erste Mal gelaufen ist) geben die
  // Beschriftung unverändert zurück.
  function resolveLabel(label, windowStartEpoch) {
    if (!label || !label.includes('{') || windowStartEpoch == null) return label;
    // Kalenderwerte der SERVERzone; als lokales Date neu aufgebaut, damit
    // isoWeekNumber() und die getMonth()-Zugriffe unten unverändert bleiben.
    const sp = window.ServerTime.parts(windowStartEpoch);
    const d = new Date(sp.year, sp.month - 1, sp.day);
    const tokenValues = {
      jahr: String(d.getFullYear()),
      jahr_kurz: String(d.getFullYear()).slice(-2),
      // Bewusst nur die Ziffer, kein "Q"-Präfix — konsistent mit den übrigen
      // numerischen Token (woche/tag/monat_nr). Wer "Q3" will, schreibt
      // "Q{quartal}"; mit eingebautem Präfix würde genau das zu "QQ3" führen.
      quartal: String(Math.floor(d.getMonth() / 3) + 1),
      monat: MONTH_NAMES[d.getMonth()],
      monat_kurz: MONTH_NAMES_SHORT[d.getMonth()],
      monat_nr: String(d.getMonth() + 1).padStart(2, '0'),
      woche: String(isoWeekNumber(d)),
      // Zweistellig wie monat_nr (01 statt 1) — konsistent mit dem
      // "DD.MM."-Format, in dem Tag/Monat sonst überall in der App erscheinen.
      tag: String(d.getDate()).padStart(2, '0'),
      // getDay(): 0 = Sonntag, daher beginnen die Namenslisten mit Sonntag.
      wochentag: WEEKDAY_NAMES[d.getDay()],
      wochentag_kurz: WEEKDAY_NAMES_SHORT[d.getDay()],
      dekade: t('{decade}er', {decade: Math.floor(d.getFullYear() / 10) * 10}),
    };
    return label.replace(LABEL_TOKEN_PATTERN, (match, token) => tokenValues[LABEL_TOKEN_ALIASES[token] || token]);
  }

  // Einfügehilfe im Editor (siehe table_editor.html) — Token + Anzeigename,
  // in der Reihenfolge, in der sie im Popover erscheinen. Eigene Liste statt
  // Object.keys() auf tokenValues in resolveLabel(), weil die Anzeige-
  // Reihenfolge (grob → fein) bewusst anders ist als der Ersetzungs-Code sie
  // bräuchte.
  // Eingefügt wird der Name in der Sprache der Oberfläche ({year} statt {jahr}).
  const LABEL_VARIABLES = [
    ['jahr', t('Jahr')], ['jahr_kurz', t('Jahr (kurz)')], ['quartal', t('Quartal')],
    ['monat', t('Monat')], ['monat_kurz', t('Monat (kurz)')], ['monat_nr', t('Monat (Nr.)')],
    ['woche', t('Woche')], ['tag', t('Tag')],
    ['wochentag', t('Wochentag')], ['wochentag_kurz', t('Wochentag (kurz)')], ['dekade', t('Dekade')],
  ].map(([token, label]) => {
    const english = Object.keys(LABEL_TOKEN_ALIASES).find((key) => LABEL_TOKEN_ALIASES[key] === token);
    return [document.documentElement.lang === 'en' ? english : token, label];
  });

  // CSS-Klassen für die Darstellungs-Optionen (Zebra/Rahmen/Dichte/Kopfzeile)
  // — dieselbe Zuordnung für die volle Tabellen-Seite UND die Dashboard-
  // Kachel, damit eine gespeicherte Tabelle an beiden Stellen gleich aussieht.
  // Die zugehörigen CSS-Regeln selbst leben lokal in jeder Seite (entities.html/
  // table_editor.html, siehe .tbl-style-* dort) — hier nur die Namenszuordnung.
  function styleClasses(style) {
    style = style || {};
    const classes = [];
    if (style.zebra) classes.push('tbl-style-zebra');
    if (style.borders === 'grid') classes.push('tbl-style-border-grid');
    else if (style.borders === 'none') classes.push('tbl-style-border-none');
    if (style.density === 'compact') classes.push('tbl-style-compact');
    if (style.header_accent) classes.push('tbl-style-header-accent');
    if (style.first_col_accent) classes.push('tbl-style-first-col-accent');
    if (style.first_col_bold) classes.push('tbl-style-first-col-bold');
    if (style.sticky_first_col) classes.push('tbl-style-sticky-first-col');
    if (style.sticky_header) classes.push('tbl-style-sticky-header');
    if (style.comparison_columns) classes.push('tbl-style-comparison-columns');
    if (style.align_units) classes.push('tbl-style-align-units');
    if (style.small_units) classes.push('tbl-style-small-units');
    if (style.align_numbers) classes.push('tbl-style-align-numbers');
    // Nur bei Abweichung vom Standard eine Klasse — Standard ist bei beiden
    // rechtsbündig (dieselbe Regel wie bisher fest im CSS), spart in den
    // meisten Fällen die Klasse.
    if (style.header_align && style.header_align !== 'right') classes.push(`tbl-style-header-align-${style.header_align}`);
    if (style.value_align && style.value_align !== 'right') classes.push(`tbl-style-value-align-${style.value_align}`);
    if (style.equal_value_cols) classes.push('tbl-style-equal-cols');
    return classes.join(' ');
  }

  return {
    evalFormula, inheritedFormulaUnit, fmtNum, cellValueText, cellUnit, cellNumberParts, cellText,
    isComparisonColumn, comparisonIndexForBase, deviationText, comparisonValueText, comparisonElapsedTimeText, percentOfTotalCell, heatmapStyle,
    rowLetters, computeValues, queryBody, computeRowSums, sumOverlap, styleClasses, currentPeriodNote, currentPeriodShortSuffix,
    resolveLabel, LABEL_VARIABLES,
  };
})();
