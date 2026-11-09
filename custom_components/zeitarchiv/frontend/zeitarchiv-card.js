// Zeitarchiv-Karte für Lovelace: ein gespeichertes Chart aus dem Zeitarchiv.
//
// Die Karte spricht nur mit Home Assistant (zwei WebSocket-Befehle der
// Integration, nur für Administratoren), nie mit der App. Gezeichnet wird mit
// dem Code der Dashboard-Kacheln der App (chart-tile-render.js, unverändert
// kopiert) und Apache ECharts.
//
// Dieser Code läuft in einer Hülle: er schreibt keine Globals in das Fenster
// von Home Assistant. Die Dateien der App erwarten ein window mit ein paar
// Hilfsobjekten (NumberFormat, TooltipHold, ServerTime) und die Namen t,
// echarts, StateEntities, PeriodNavigation; sie werden hier in einem eigenen
// Geltungsbereich mit einem nachgebauten window ausgewertet, ECharts als
// CommonJS-Modul. So bleibt die Darstellung identisch zur App, ohne dass ein
// Update der App Dateien doppelt pflegen lässt: frontend/ enthält unveränderte
// Kopien, ein Test der Entwicklung vergleicht sie.

const BASE = new URL('.', import.meta.url).href;
const VERSION_QUERY = new URL(import.meta.url).search;

const TEXTS = {
  de: {
    loading: 'Lade …',
    chartLabel: 'Diagramm {title}', sum: 'Summe', last: 'zuletzt', more: 'und {n} weitere',
    noData: 'Keine Daten',
    chooseChart: 'Bitte ein Chart, eine Tabelle, einen Baustein oder Entitäten aus dem Zeitarchiv wählen.',
    noVisible: 'Die Tabelle hat keine sichtbaren Zeilen oder Spalten.',
    unsupported: 'Diese Darstellung zeigt die Karte noch nicht.',
    stale: 'Stand vor {min} Min, Zeitarchiv nicht erreichbar',
    not_loaded: 'Keine Zeitarchiv-Verbindung eingerichtet.',
    app_outdated: 'Die Zeitarchiv-App ist zu alt für die Karte. Bitte die App aktualisieren.',
    not_found: 'Dieses Chart, diese Tabelle oder eine der Entitäten gibt es im Zeitarchiv nicht (mehr).',
    invalid: 'Die App hat die Angaben der Karte abgelehnt.',
    too_large: 'Für diesen Zeitraum gibt es zu viele Datenpunkte. Bitte einen kürzeren Zeitraum wählen.',
    busy: 'Zeitarchiv ist gerade beschäftigt, nächster Versuch folgt.',
    auth_failed: 'Zeitarchiv hat die Zugangsdaten abgelehnt.',
    unreachable: 'Zeitarchiv ist nicht erreichbar.',
    app_error: 'Zeitarchiv hat einen Fehler gemeldet. Details stehen im Protokoll der App.',
    staleError: 'Fehler in Zeitarchiv · Stand vor {min} Min',
    notShared: 'Nicht freigegeben: Andere Benutzer sehen diese Karte nicht. Freigabe in den Einstellungen der Integration unter „Karte freigeben“.',
    entitiesAdminOnly: 'Entitäten direkt sehen nur Administratoren. Für andere Benutzer ein gespeichertes Chart freigeben.',
    unauthorized: 'Für dich nicht freigegeben. Ein Administrator kann Charts und Tabellen in den Einstellungen der Integration unter „Karte freigeben“ freigeben.',
    unknown: 'Die Karte konnte nicht geladen werden.',
    spec: 'Die Karte passt nicht zur Version der Zeitarchiv-App.',
    script: 'Die Karte konnte ihre Dateien nicht laden.',
    source: 'Quelle',
    sourceChart: 'Gespeichertes Chart',
    sourceTable: 'Gespeicherte Tabelle',
    table_id: 'Tabelle aus dem Zeitarchiv',
    sourceEntities: 'Entitäten direkt',
    sourceElement: 'Dashboard-Baustein',
    element: 'Baustein',
    element_columns: 'Spalten',
    element_vorjahr: 'Mit Vorjahr vergleichen',
    element_diff: 'Differenz anzeigen',
    column_heute: 'Heute', column_gestern: 'Gestern', column_monat: 'Dieser Monat', column_vormonat: 'Letzter Monat', column_jahr: 'Dieses Jahr',
    not_configured: 'Dieser Baustein ist in der Zeitarchiv-App nicht eingerichtet.',
    elementsNone: 'In der Zeitarchiv-App ist noch kein Baustein eingerichtet.',
    elementsOutdated: 'Die Integration kennt diesen Baustein nicht. Bitte die Integration aktualisieren.',
    elementAdminOnly: 'Dashboard-Bausteine sehen nur Administratoren.',
    element_offset: 'Perioden zurück (0 = aktuell)', element_side: 'Seite', element_follow: 'Datumsauswahl der Energie von Home Assistant folgen',
    side_verbrauch: 'Verbrauch', side_versorgung: 'Versorgung',
    element_values: 'Werte', element_sparkline: 'Verlauf anzeigen',
    element_metric: 'Kennzahl', element_band: 'Spanne der Jahre anzeigen',
    metric_temperature: 'Temperatur', metric_precip: 'Niederschlag', metric_sun: 'Sonnenstunden',
    metric_avg: 'Temperatur Ø', metric_max: 'Temperatur Max', metric_min: 'Temperatur Min',
    element_role: 'Wert', element_years: 'Jahre', element_group: 'Gruppe',
    group_basis: 'Übersicht', group_wind: 'Wind und Sonne', group_klima: 'Temperatur und Klima',
    role_erzeugung: 'Erzeugung', role_einspeisung: 'Einspeisung', role_netzbezug: 'Netzbezug', role_verbrauch: 'Verbrauch',
    years_5: 'Letzte 5', years_10: 'Letzte 10', years_0: 'Alle',
    element_mode: 'Zählung', mode_bis_jetzt: 'Bis heute', mode_komplett: 'Ganze Zeiträume', element_limit: 'Anzahl',
    chart_id: 'Chart aus dem Zeitarchiv',
    entities: 'Entitäten (nur archivierte)',
    period: 'Zeitraum',
    style: 'Darstellung',
    period_saved: 'Wie im Chart gespeichert',
    legend: 'Legende anzeigen',
    legend_style: 'Legenden-Stil', legendStyle_chart: 'Wie im Chart', legendStyle_chips: 'Chips', legendStyle_table: 'Tabelle', legendStyle_off: 'Aus',
    legend_size: 'Legendengröße', legendSize_chart: 'Wie im Chart', legendSize_normal: 'Normal', legendSize_small: 'Klein',
    legend_metrics: 'Kennzahlen der Legende (leer: wie im Chart)',
    metric_last: 'Aktuell', metric_min: 'Min', metric_max: 'Max', metric_average: 'Durchschnitt', metric_sum: 'Summe',
    period_day: 'Heute',
    period_week: 'Diese Woche',
    period_month: 'Dieser Monat',
    period_year: 'Dieses Jahr',
    period_24h: 'Letzte 24 Stunden',
    period_7d: 'Letzte 7 Tage',
    period_30d: 'Letzte 30 Tage',
    style_auto: 'Je Entität (Linie oder Balken)',
    style_stacked: 'Gestapelte Balken',
    style_percent: 'Anteile in Prozent',
    title: 'Titel (leer: Name des Charts)',
    title_element: 'Titel (leer: Name des Bausteins)',
    title_table: 'Titel (leer: Name der Tabelle)',
    period_group: 'Zeitraum und Versatz',
    legend_more: 'Legende anpassen',
    'desc_energie.zeitraeume': 'Energiewerte für Monat, Vormonat und Jahr im Vergleich, auf Wunsch mit dem Vorjahr und der Differenz.',
    'desc_energie.matrix': 'Eine Energiegröße je Monat und Jahr als Tabelle (Jahre × Monate).',
    'desc_energie.monatsvergleich': 'Die Monatswerte einer Energiegröße über mehrere Jahre im Vergleich.',
    'desc_energie.anteile': 'Anteile der Verbraucher oder der Versorgung für einen Zeitraum.',
    'desc_energie.kennzahlen': 'Kacheln mit Energiemengen und dem Vergleich zur Vorperiode, wahlweise mit Verlauf; auch Autarkie und Eigenverbrauch.',
    'desc_energie.speicher': 'Der Batteriespeicher mit Ladestand; bei einem Tag mit der Kurve des Ladestands.',
    'desc_energie.rekorde': 'Rekorde der Energie, etwa der stärkste Erzeugungstag, die höchste Einspeisung und der höchste Verbrauch.',
    'desc_energie.kenntage': 'Kenntage je Jahr; wählbar sind die Jahre und „bis heute“ oder ganze Jahre.',
    'desc_energie.veraenderungen': 'Was sich bei den Verbrauchern verändert hat; die Zahl der Verbraucher ist wählbar.',
    'desc_energie.heatmap': 'Das Tageslastprofil der Energie als Heatmap über eine Woche, einen Monat oder ein Jahr.',
    'desc_wetter.kennzahlen': 'Kacheln mit den aktuellen Wetterwerten; welche, ist wählbar.',
    'desc_wetter.monatsvergleich': 'Die Monatswerte einer Wettergröße (Temperatur, Niederschlag, Sonne) über mehrere Jahre im Vergleich.',
    'desc_wetter.matrix': 'Die Jahresübersicht des Wetters als Heatmap, Tag für Tag.',
    'desc_wetter.zeitraeume': 'Wetterwerte für heute, gestern, Monat, Vormonat und Jahr, auf Wunsch mit dem Vorjahr; die Gruppe bestimmt die Werte.',
    moreSettings: 'Weitere Einstellungen',
    help_vorjahr: 'Zeigt zu jeder Spalte daneben den Wert des Vorjahres.',
    help_diff: 'Zeigt unter dem Wert die Veränderung zum Vorjahr. Braucht „Mit Vorjahr vergleichen“.',
    help_offset: '0 ist der aktuelle Zeitraum, −1 der davor.',
    help_follow: 'Zeitraum und Versatz folgen dann der Datumsauswahl im Energie-Dashboard von Home Assistant.',
    refresh: 'Aktualisierung',
    help_refresh: 'Leer: 60 Sekunden, mindestens 15.',
    height: 'Höhe',
    help_height: 'Leer: bei Charts 260 Pixel, bei Tabellen und Bausteinen so hoch wie der Inhalt.',
    tap_action: 'Beim Tippen',
    notSupportedShort: 'noch nicht darstellbar',
    description: 'Zeigt Charts, Tabellen und Entitäten aus dem Zeitarchiv sowie Bausteine aus den Dashboards der App (Energie und Wetter).',
  },
  en: {
    loading: 'Loading …',
    chartLabel: 'Chart {title}', sum: 'total', last: 'latest', more: 'and {n} more',
    noData: 'No data',
    chooseChart: 'Please choose a chart, a table, an element or entities from Zeitarchiv.',
    noVisible: 'The table has no visible rows or columns.',
    unsupported: 'The card cannot show this kind of chart yet.',
    stale: 'As of {min} min ago, Zeitarchiv not reachable',
    not_loaded: 'No Zeitarchiv connection is set up.',
    app_outdated: 'The Zeitarchiv app is too old for the card. Please update the app.',
    not_found: 'This chart, table or one of the entities no longer exists in Zeitarchiv.',
    invalid: 'The app rejected the settings of the card.',
    too_large: 'There are too many data points for this period. Please choose a shorter period.',
    busy: 'Zeitarchiv is busy, trying again shortly.',
    auth_failed: 'Zeitarchiv rejected the credentials.',
    unreachable: 'Zeitarchiv is not reachable.',
    app_error: 'Zeitarchiv reported an error. Details are in the app log.',
    staleError: 'Error in Zeitarchiv · as of {min} min ago',
    notShared: 'Not shared: other users will not see this card. Share it in the integration settings under “Share card”.',
    entitiesAdminOnly: 'Entities directly are visible to administrators only. Share a saved chart for other users.',
    unauthorized: 'Not shared with you. An administrator can share charts and tables in the integration settings under “Share card”.',
    unknown: 'The card could not be loaded.',
    spec: 'The card does not match the version of the Zeitarchiv app.',
    script: 'The card could not load its files.',
    source: 'Source',
    sourceChart: 'Saved chart',
    sourceTable: 'Saved table',
    table_id: 'Table from Zeitarchiv',
    sourceEntities: 'Entities directly',
    sourceElement: 'Dashboard element',
    element: 'Element',
    element_columns: 'Columns',
    element_vorjahr: 'Compare with last year',
    element_diff: 'Show difference',
    column_heute: 'Today', column_gestern: 'Yesterday', column_monat: 'This month', column_vormonat: 'Last month', column_jahr: 'This year',
    not_configured: 'This element is not set up in the Zeitarchiv app.',
    elementsNone: 'No element is set up in the Zeitarchiv app yet.',
    elementsOutdated: 'The integration does not know this element. Please update the integration.',
    elementAdminOnly: 'Dashboard elements are visible to administrators only.',
    element_offset: 'Periods back (0 = current)', element_side: 'Side', element_follow: 'Follow the date selection of the Home Assistant energy dashboard',
    side_verbrauch: 'Consumption', side_versorgung: 'Supply',
    element_values: 'Values', element_sparkline: 'Show trend',
    element_metric: 'Measure', element_band: 'Show range of years',
    metric_temperature: 'Temperature', metric_precip: 'Precipitation', metric_sun: 'Sunshine hours',
    metric_avg: 'Temperature avg.', metric_max: 'Temperature max.', metric_min: 'Temperature min.',
    element_role: 'Value', element_years: 'Years', element_group: 'Group',
    group_basis: 'Overview', group_wind: 'Wind and sun', group_klima: 'Temperature and climate',
    role_erzeugung: 'Generation', role_einspeisung: 'Feed-in', role_netzbezug: 'Grid import', role_verbrauch: 'Consumption',
    years_5: 'Last 5', years_10: 'Last 10', years_0: 'All',
    element_mode: 'Counting', mode_bis_jetzt: 'Until today', mode_komplett: 'Complete periods', element_limit: 'Number',
    chart_id: 'Chart from Zeitarchiv',
    entities: 'Entities (archived only)',
    period: 'Period',
    style: 'Display',
    period_saved: 'As saved in the chart',
    legend: 'Show legend',
    legend_style: 'Legend style', legendStyle_chart: 'As in the chart', legendStyle_chips: 'Chips', legendStyle_table: 'Table', legendStyle_off: 'Off',
    legend_size: 'Legend size', legendSize_chart: 'As in the chart', legendSize_normal: 'Normal', legendSize_small: 'Small',
    legend_metrics: 'Legend values (empty: as in the chart)',
    metric_last: 'Current', metric_min: 'Min', metric_max: 'Max', metric_average: 'Average', metric_sum: 'Total',
    period_day: 'Today',
    period_week: 'This week',
    period_month: 'This month',
    period_year: 'This year',
    period_24h: 'Last 24 hours',
    period_7d: 'Last 7 days',
    period_30d: 'Last 30 days',
    style_auto: 'Per entity (line or bars)',
    style_stacked: 'Stacked bars',
    style_percent: 'Shares in percent',
    title: 'Title (empty: chart name)',
    title_element: 'Title (empty: element name)',
    title_table: 'Title (empty: table name)',
    period_group: 'Period and offset',
    legend_more: 'Customize legend',
    'desc_energie.zeitraeume': 'Energy values for this month, last month and this year compared, optionally with the previous year and the difference.',
    'desc_energie.matrix': 'One energy measure per month and year as a table (years × months).',
    'desc_energie.monatsvergleich': 'The monthly values of one energy measure compared over several years.',
    'desc_energie.anteile': 'Shares of the consumers or of the supply for a period.',
    'desc_energie.kennzahlen': 'Tiles with energy amounts and the comparison with the previous period, optionally with a trend; also self-sufficiency and self-consumption.',
    'desc_energie.speicher': 'The battery storage with its charge level; for a day with the curve of the state of charge.',
    'desc_energie.rekorde': 'Energy records, such as the strongest generation day, the highest feed-in and the highest consumption.',
    'desc_energie.kenntage': 'Key days per year; you choose the years and "until today" or whole years.',
    'desc_energie.veraenderungen': 'What has changed among the consumers; the number of consumers is selectable.',
    'desc_energie.heatmap': 'The daily load profile of the energy as a heatmap over a week, a month or a year.',
    'desc_wetter.kennzahlen': 'Tiles with the current weather values; which ones is selectable.',
    'desc_wetter.monatsvergleich': 'The monthly values of a weather measure (temperature, precipitation, sun) compared over several years.',
    'desc_wetter.matrix': 'The weather year overview as a heatmap, day by day.',
    'desc_wetter.zeitraeume': 'Weather values for today, yesterday, this month, last month and this year, optionally with the previous year; the group determines the values.',
    moreSettings: 'More settings',
    help_vorjahr: 'Shows the value of the previous year next to each column.',
    help_diff: 'Shows the change from the previous year below the value. Needs "Compare with last year".',
    help_offset: '0 is the current period, −1 the one before.',
    help_follow: 'Period and offset then follow the date selection of the Home Assistant energy dashboard.',
    refresh: 'Refresh',
    help_refresh: 'Empty: 60 seconds, at least 15.',
    height: 'Height',
    help_height: 'Empty: 260 pixels for charts, as tall as the content for tables and elements.',
    tap_action: 'On tap',
    notSupportedShort: 'not supported yet',
    description: 'Shows charts, tables and entities from Zeitarchiv, plus elements from the app dashboards (energy and weather).',
  },
};

// Felder der Bausteine im Editor-Schema; ihre Beschriftungen heißen element_<Name> (siehe _fieldLabel).
const ELEMENT_FIELDS = new Set(['role', 'years', 'mode', 'limit', 'metric', 'band', 'values', 'sparkline', 'side', 'offset', 'group', 'columns', 'vorjahr', 'diff']);

// Die Fassung des Vertrags mit der App (card_routes.SPEC_VERSION).
const SPEC_VERSION = 1;

// Home-Assistant-Farbschema der App (--chart-1 bis --chart-8, hell und dunkel).
const PALETTES = {
  light: ['#009AC7', '#C94E00', '#00883C', '#8A5FC7', '#DC3146', '#18BCF2', '#B77A00', '#5E5E5E'],
  dark: ['#37C8FD', '#FF9342', '#5DC36F', '#B99AF0', '#FD8F90', '#7BD4FB', '#FFD166', '#B1B1B1'],
};

const text = (hass, key, values) => {
  const table = (hass?.locale?.language || hass?.language || 'en').startsWith('de') ? TEXTS.de : TEXTS.en;
  let result = table[key] ?? TEXTS.en[key] ?? key;
  if (values) result = result.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
  return result;
};

// Abstand bis zum nächsten Abruf in Sekunden: im Normalfall die eingestellte
// Aktualisierung, nach Fehlern 10, 20, 40 … Sekunden, nie mehr als die Aktualisierung.
// Ein Ausfall der App wird so schnell bemerkt, ohne sie bei längerem Ausfall zu bedrängen.
const retryDelaySeconds = (failures, refresh) => {
  const normal = Math.max(15, Number(refresh) || 60);
  return failures > 0 ? Math.min(normal, 10 * 2 ** (failures - 1)) : normal;
};

// --- Laufzeit: Dateien laden und in der Hülle auswerten ---------------------------------

let sourcesPromise = null;
const runtimes = new Map();

const fetchText = async (name) => {
  const response = await fetch(`${BASE}${name}${VERSION_QUERY}`);
  if (!response.ok) throw new Error(`${name}: ${response.status}`);
  return response.text();
};

const loadSources = () => {
  sourcesPromise ||= (async () => {
    const [echartsSource, render, numberFormat, tooltipHold, serverTime, htmlEscape, stateEntities, tableCompute, tableRender, elementTableRender, elementChartRender, elementKpiRender, legendRender, tableCss, catalog] = await Promise.all([
      fetchText('echarts.min.js'), fetchText('chart-tile-render.js'), fetchText('number-format.js'),
      fetchText('tooltip-hold.js'), fetchText('server-time.js'), fetchText('html-escape.js'),
      fetchText('state-entities.js'), fetchText('table-compute.js'), fetchText('table-tile-render.js'), fetchText('element-table-render.js'), fetchText('element-chart-render.js'), fetchText('element-kpi-render.js'), fetchText('legend-render.js'),
      fetchText('table.css'), fetchText('catalog.json'),
    ]);
    const module = {exports: {}};
    new Function('module', 'exports', `${echartsSource}\n//# sourceURL=zeitarchiv/echarts.min.js`).call(module.exports, module, module.exports);
    return {echarts: module.exports, render, numberFormat, tooltipHold, serverTime, htmlEscape, stateEntities, tableCompute, tableRender, elementTableRender, elementChartRender, elementKpiRender, legendRender, tableCss, catalog: JSON.parse(catalog)};
  })().catch((err) => { sourcesPromise = null; throw err; });
  return sourcesPromise;
};

// Mit sourceURL, damit Fehler in den ausgewerteten Dateien in der Konsole ihren Dateinamen tragen.
const evaluate = (source, names, values, file) => new Function(...names, `${source}\n//# sourceURL=zeitarchiv/${file}`)(...values);

const buildRuntime = (sources, {timezone, language, dark}) => {
  const palette = dark ? PALETTES.dark : PALETTES.light;
  const win = {ZA_FORMAT: language};
  // Nur das, was die Dateien der App vom Dokument brauchen: die Zeitzone, das Format und Canvas-Elemente
  // (state-entities.js zeichnet damit das Füllmuster für „nicht verfügbar“).
  const doc = {
    documentElement: {dataset: {tz: timezone, format: language}, lang: String(language).startsWith('de') ? 'de' : 'en'}, body: {},
    createElement: (tag) => document.createElement(tag),
  };
  // Farben aus dem CSS der App (--chart-1 …) und Werte aus dem Thema von Home Assistant, die die Karte
  // vor jedem Zeichnen setzt (setVars).
  const vars = {};
  const getComputedStyle = () => ({
    getPropertyValue: (name) => {
      const match = /^--chart-(\d)$/.exec(name);
      if (match) return palette[Number(match[1]) - 1] || '';
      if (name in vars) return vars[name];
      return name === '--font-scale' ? '1' : '';
    },
  });
  // Die Schlüssel der Zeichenregeln sind deutsch (wie t() der App); außer für Deutsch kommt der
  // englische Text aus catalog.json (scripts/sync_card_assets.py), ohne Eintrag bleibt der Schlüssel.
  const dictionary = String(language).startsWith('de') ? {} : (sources.catalog.en || {});
  const t = (value, values) => {
    let result = Object.prototype.hasOwnProperty.call(dictionary, value) ? dictionary[value] : value;
    if (values) result = result.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
    return result;
  };
  evaluate(sources.numberFormat, ['window', 'document'], [win, doc], 'number-format.js');
  evaluate(sources.tooltipHold, ['window', 'document', 't', 'NumberFormat'], [win, doc, t, win.NumberFormat], 'tooltip-hold.js');
  evaluate(sources.serverTime, ['window', 'document'], [win, doc], 'server-time.js');
  evaluate(sources.htmlEscape, ['window'], [win], 'html-escape.js');
  evaluate(sources.stateEntities, ['window', 'document', 'getComputedStyle', 't', 'NumberFormat', 'escapeHtml'],
    [win, doc, getComputedStyle, t, win.NumberFormat, win.escapeHtml], 'state-entities.js');
  const render = evaluate(
    `${sources.render}\nreturn window.ChartTileRender;`,
    ['window', 'document', 'getComputedStyle', 't', 'NumberFormat', 'TooltipHold', 'StateEntities', 'PeriodNavigation', 'echarts', 'escapeHtml'],
    [win, doc, getComputedStyle, t, win.NumberFormat, win.TooltipHold, win.StateEntities, {}, sources.echarts, win.escapeHtml],
    'chart-tile-render.js',
  );
  // Tabellen: dieselben Dateien wie die Tabellen-Kachel der App.
  evaluate(sources.tableCompute, ['window', 'document', 't'], [win, doc, t], 'table-compute.js');
  const TableTileRender = evaluate(
    `${sources.tableRender}\nreturn window.TableTileRender;`,
    ['window', 't', 'escapeHtml', 'TableCompute'], [win, t, win.escapeHtml, win.TableCompute], 'table-tile-render.js',
  );
  // Bausteine der Dashboards (Roadmap 1.48): dieselbe Datei zeichnet die Tabelle im Dashboard der App.
  const ElementTableRender = evaluate(
    `${sources.elementTableRender}\nreturn window.ElementTableRender;`,
    ['window', 't', 'escapeHtml', 'NumberFormat', 'ServerTime'], [win, t, win.escapeHtml, win.NumberFormat, win.ServerTime], 'element-table-render.js',
  );
  // Legende mit Werten (Roadmap 1.49): dieselbe Datei wie die Kachel der App; braucht ChartTileRender im window.
  const LegendRender = evaluate(
    `${sources.legendRender}\nreturn window.LegendRender;`,
    ['window', 't', 'escapeHtml', 'NumberFormat'], [win, t, win.escapeHtml, win.NumberFormat], 'legend-render.js',
  );
  // Diagramme der Bausteine: liefern nur die ECharts-Optionen; Instanz und Farben stellt die Karte.
  const ElementChartRender = evaluate(
    `${sources.elementChartRender}\nreturn window.ElementChartRender;`,
    ['window', 't', 'escapeHtml', 'NumberFormat'], [win, t, win.escapeHtml, win.NumberFormat], 'element-chart-render.js',
  );
  // Kennzahlen-Kacheln der Bausteine: HTML mit Verlauf als SVG, ohne ECharts.
  const ElementKpiRender = evaluate(
    `${sources.elementKpiRender}\nreturn window.ElementKpiRender;`,
    ['window', 't', 'escapeHtml', 'NumberFormat'], [win, t, win.escapeHtml, win.NumberFormat], 'element-kpi-render.js',
  );
  return {render, setVars: (map) => Object.assign(vars, map), tables: {TableCompute: win.TableCompute, TableTileRender}, ElementTableRender, ElementChartRender, ElementKpiRender, LegendRender};
};

const runtimeFor = async (settings) => {
  const sources = await loadSources();
  const key = `${settings.timezone}|${settings.language}|${settings.dark}`;
  if (!runtimes.has(key)) runtimes.set(key, buildRuntime(sources, settings));
  return {...runtimes.get(key), echarts: sources.echarts, tableCss: sources.tableCss};
};

// --- Karte -----------------------------------------------------------------------------

// Reihenfolge der Kennzahlen wie in legend-render.js; unbekannte Schlüssel aus der Konfiguration fallen weg.
const LEGEND_KEYS = ['last', 'min', 'max', 'average', 'sum'];
// Unterhalb dieser Kartenbreite zeigt "wie das Chart" statt einer Tabelle Chips.
const NARROW_CARD_PX = 300;

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  ha-card.clickable { cursor: pointer; }
  ha-card.clickable:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
  .header { padding: 12px 16px 0; font-size: var(--ha-card-header-font-size, 18px); font-weight: 500; color: var(--primary-text-color); }
  .body { position: relative; padding: 8px 8px 12px; }
  .chart { width: 100%; }
  .note { padding: 16px; color: var(--secondary-text-color); }
  .note.error { color: var(--error-color); }
  .badge { display: inline-block; margin: 0 16px 8px; padding: 2px 10px; border-radius: 999px; font-size: 12px;
           color: var(--warning-color, #b26a00); border: 1px solid currentColor; }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 4px 8px 0; font-size: 13px; color: var(--primary-text-color); }
  .legend-item { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; background: none; border: 0; padding: 2px 0;
                 font: inherit; color: inherit; }
  .legend-item.inactive { opacity: .45; text-decoration: line-through; }
  .legend.values { display: block; padding: 4px 8px 0; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .tablebox { overflow: auto; padding: 4px 8px 12px; color: var(--primary-text-color); }
  .tablebox table { margin: 0; }
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; padding: 4px 0; }
  .kpi-tile { padding: 8px 10px; border-radius: 8px; background: var(--secondary-background-color, rgba(127, 127, 127, .08)); min-width: 0; }
  .kpi-label { font-size: 12px; color: var(--secondary-text-color); }
  .kpi-value { font-size: 22px; font-weight: 500; line-height: 1.25; color: var(--primary-text-color); }
  .kpi-unit { font-size: 13px; font-weight: 400; margin-left: 3px; color: var(--secondary-text-color); }
  .kpi-sub { font-size: 12px; color: var(--secondary-text-color); }
  .kpi-sub small { font-size: 11px; opacity: .8; }
  .kpi-delta.kpi-good { color: var(--success-color, #43a047); }
  .kpi-delta.kpi-bad { color: var(--error-color, #db4437); }
  .kpi-spark { display: block; width: 100%; height: 26px; margin-top: 4px; color: var(--primary-color); }
  .stor-head { display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }
  .stor-batt { width: 52px; height: 24px; flex: none; color: var(--primary-color); }
  .kpi-empty { padding: 12px; color: var(--secondary-text-color); }
  [hidden] { display: none !important; }
  /* Variablen der App für die Tabelle, aus dem Thema von Home Assistant */
  :host {
    --ink: var(--primary-text-color); --ink-muted: var(--secondary-text-color); --ink-faint: var(--secondary-text-color);
    --border: var(--divider-color); --border-strong: var(--divider-color); --surface: var(--card-background-color);
    --surface-alt: var(--secondary-background-color, rgba(127, 127, 127, .08)); --accent-line: var(--primary-color);
    --accent-bar: var(--primary-color); --accent-contrast: var(--text-primary-color, #fff); --danger: var(--error-color, #db4437);
    --danger-soft: rgba(219, 68, 55, .12); --warning-soft: rgba(255, 152, 0, .15); --shadow: none;
    --font-display: var(--ha-font-family-body, Roboto, sans-serif); --font-mono: var(--ha-font-family-body, Roboto, sans-serif);
    --bg: var(--card-background-color, #fff); --font-scale: 1;
    --positive: var(--success-color, #43a047); --chart-1: var(--primary-color);
  }
`;

const PERIODS = ['month', 'day', 'week', 'year', '24h', '7d', '30d'];

class ZeitarchivCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._config = null;
    this._hass = null;
    this._chart = null;
    this._timer = null;
    this._visible = true;
    this._loading = false;
    this._generation = 0;
    this._reload = false;
    this._shown = false;
    this._hidden = new Set();
    this._lastGood = 0;
    this._failures = 0;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card>
        <div class="header" part="header" hidden></div>
        <div class="body">
          <div class="chart" role="img" hidden></div>
          <div class="legend" hidden></div>
          <div class="tablebox" hidden></div>
          <style class="tablecss"></style>
          <div class="note" role="status"></div>
        </div>
        <div class="badge" role="status" hidden></div>
      </ha-card>`;
    this._els = {
      header: this.shadowRoot.querySelector('.header'), legend: this.shadowRoot.querySelector('.legend'), chart: this.shadowRoot.querySelector('.chart'),
      note: this.shadowRoot.querySelector('.note'), badge: this.shadowRoot.querySelector('.badge'),
      table: this.shadowRoot.querySelector('.tablebox'),
      tableCss: this.shadowRoot.querySelector('.tablecss'),
    };
    this._els.card = this.shadowRoot.querySelector('ha-card');
    this._wireTableTips();
    this._wireAction();
    this._wireLegend();
  }

  // Tippen: die Standard-Aktion von Home Assistant (tap_action). Die Karte löst nur das Ereignis aus,
  // das Öffnen eines Dashboards, einer URL oder einer Aktion erledigt HA. Ohne Aktion ändert sich nichts.
  _wireAction() {
    const card = this._els.card;
    card.addEventListener('click', () => this._fireAction());
    card.addEventListener('keydown', (event) => {
      // Nur, wenn die Karte selbst den Fokus hat: Enter/Leertaste auf einem Legendeneintrag bubbelte sonst hierher,
      // löste die tap_action aus und verhinderte mit preventDefault() das Umschalten der Serie.
      if (event.target !== card) return;
      if ((event.key === 'Enter' || event.key === ' ') && this._actionOn()) { event.preventDefault(); this._fireAction(); }
    });
  }

  _actionOn() {
    const action = this._config?.tap_action?.action;
    return Boolean(action) && action !== 'none';
  }

  _fireAction() {
    if (!this._actionOn()) return;
    // Bei Entitäten direkt gilt die erste als Ziel von "Mehr Informationen".
    const entity = this._config.entities?.[0];
    this.dispatchEvent(new CustomEvent('hass-action', {
      bubbles: true,
      composed: true,
      detail: {config: {...(entity ? {entity} : {}), tap_action: this._config.tap_action}, action: 'tap'},
    }));
  }

  // Als Schaltfläche kennzeichnen (Tastatur, Screenreader). Der Beschriftungstext ist der des Charts, weil eine
  // Schaltfläche ihren Inhalt für Screenreader zusammenfasst.
  _applyAction() {
    const card = this._els.card;
    const on = this._actionOn();
    card.classList.toggle('clickable', on);
    if (!on) { card.removeAttribute('role'); card.removeAttribute('tabindex'); card.removeAttribute('aria-label'); return; }
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    const label = this._els.chart.getAttribute('aria-label') || this._els.header.textContent;
    if (label) card.setAttribute('aria-label', label);
  }

  // Hinweise der Tabelle (data-tooltip-fixed). fixed-tooltip.js der App lauscht am document.body und sähe im
  // Shadow-DOM nur den Host; hier derselbe Hinweis (gleiche Klasse, gleiche Verzögerung), im Shadow-DOM der Karte.
  _wireTableTips() {
    const box = this._els.table;
    let timer = null;
    let tip = null;
    let target = null;
    const hide = () => {
      clearTimeout(timer);
      timer = null;
      tip?.remove();
      tip = null;
      target = null;
    };
    const show = (el) => {
      tip = document.createElement('div');
      tip.className = 'dtile-tooltip-fixed';
      tip.textContent = el.getAttribute('data-tooltip-fixed');
      target = el;
      this.shadowRoot.appendChild(tip);
      const rect = el.getBoundingClientRect();
      const size = tip.getBoundingClientRect();
      tip.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - size.width - 8))}px`;
      const above = rect.top - size.height - 6;
      tip.style.top = `${above < 8 ? rect.bottom + 6 : above}px`;
    };
    box.addEventListener('mouseover', (event) => {
      const el = event.target.closest?.('[data-tooltip-fixed]');
      if (!el || el === target) return;
      hide();
      if (el.getAttribute('data-tooltip-fixed')) timer = setTimeout(() => show(el), 600);
    });
    box.addEventListener('mouseout', (event) => {
      if (event.target.closest?.('[data-tooltip-fixed]')) hide();
    });
    box.addEventListener('scroll', hide);
    this._hideTableTip = hide;
  }

  static getConfigElement() { return document.createElement('zeitarchiv-card-editor'); }

  // Der Kartenwähler zeigt die Karte mit dieser Konfiguration als Vorschau: das erste darstellbare gespeicherte
  // Chart, sonst die erste Tabelle. Ohne Rechte, ohne App oder bei einer langsamen Antwort bleibt sie leer
  // (dann zeigt die Vorschau den Hinweis „Chart wählen“).
  static async getStubConfig(hass) {
    try {
      const listed = await Promise.race([
        hass.callWS({type: 'zeitarchiv/card/items'}),
        new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 3000)),
      ]);
      const chart = (listed.items || []).find((item) => item.supported);
      if (chart) return {chart_id: chart.id};
      const table = (listed.tables || [])[0];
      if (table) return {table_id: table.id};
    } catch (err) {
      // Vorschau bleibt leer.
    }
    return {};
  }

  setConfig(config) {
    this._config = {refresh: 60, height: 260, ...config};
    if (this._config.chart_id != null) this._config.chart_id = Number(this._config.chart_id);
    if (this._config.table_id != null) this._config.table_id = Number(this._config.table_id);
    this._explicitHeight = config.height != null;
    this._config.entities = Array.isArray(config.entities) ? config.entities.filter((id) => typeof id === 'string' && id) : [];
    this._els.chart.style.height = `${Math.max(120, Number(this._config.height) || 260)}px`;
    this._hidden.clear();
    this._lastGood = 0;
    this._failures = 0;
    this._generation += 1;
    this._applyAction();
    this._followEnergy();
    if (this._hass) this._load();
    else this._showNote(this._hasSource() ? 'loading' : 'chooseChart');
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this._config) { this._look = this._lookOf(hass); this._followEnergy(); this._load(); return; }
    // Hell/Dunkel, Thema oder Sprache gewechselt: neu zeichnen, statt bis zur nächsten Aktualisierung
    // (bis zu einer Stunde) mit den alten Farben stehen zu bleiben. Die Antwort kommt meist aus dem Cache.
    const look = this._lookOf(hass);
    if (this._look !== look) {
      this._look = look;
      if (this._config && this._shown) this._load();
    }
  }

  _lookOf(hass) {
    return `${hass?.themes?.darkMode}|${hass?.themes?.theme}|${hass?.locale?.language || hass?.language}`;
  }

  // Abschnittsansicht: volle Breite (mindestens die halbe), die Höhe ergibt sich aus der Karte selbst
  // (Chart mit der eingestellten Höhe, Tabelle mit ihren Zeilen) statt aus einer festen Zeilenzahl.
  getGridOptions() { return {columns: 12, min_columns: 6, rows: 'auto'}; }

  getCardSize() { return Math.ceil((Number(this._config?.height) || 260) / 50) + 1; }

  connectedCallback() {
    window.addEventListener('scroll', this._hideTableTip, true);
    if (typeof IntersectionObserver !== 'undefined') {
      this._observer = new IntersectionObserver((entries) => {
        this._visible = entries.some((entry) => entry.isIntersecting);
        if (this._visible && this._stale()) this._load();
      });
      this._observer.observe(this);
    }
    if (typeof ResizeObserver !== 'undefined') {
      this._resize = new ResizeObserver(() => { this._chart?.resize(); this._restyleLegend(); });
      this._resize.observe(this._els.chart);
    }
    // disconnectedCallback meldet das Abo ab; wird die Karte wieder eingehängt (Ansichtswechsel, Bearbeitungsmodus), muss es neu entstehen.
    if (this._hass && this._config) { this._followEnergy(); this._load(); }
  }

  disconnectedCallback() {
    clearTimeout(this._timer);
    this._timer = null;
    this._unfollow?.();
    this._unfollow = null;
    this._observer?.disconnect();
    window.removeEventListener('scroll', this._hideTableTip, true);
    this._hideTableTip();
    this._resize?.disconnect();
    if (this._chart) { this._chart.dispose(); this._chart = null; }
  }

  _hasSource() {
    return Boolean(this._config?.entities?.length || this._config?.chart_id || this._config?.table_id || this._config?.element);
  }

  // Die Anfrage an Home Assistant: Entitäten direkt oder ein gespeichertes Chart.
  _request() {
    const config = this._config;
    // Breite der Karte: der Zeitstrahl in Jahr und Dekade wird in dieser Breite vom Server zusammengefasst.
    const px = Math.min(4000, Math.max(0, Math.round(this.getBoundingClientRect().width)));
    if (config.entities.length) {
      return {type: 'zeitarchiv/card/series', entity_ids: config.entities, period: config.period || 'month', style: config.style || 'auto', px};
    }
    if (config.element) {
      const request = {type: 'zeitarchiv/card/element', key: config.element};
      if (Array.isArray(config.columns) && config.columns.length) request.columns = config.columns;
      if (config.vorjahr === false) request.vorjahr = false;
      if (config.role) request.role = config.role;
      if (config.group) request.group = config.group;
      if (config.metric) request.metric = config.metric;
      if (config.side) request.side = config.side;
      if (Array.isArray(config.values) && config.values.length) request.values = config.values;
      if (config.sparkline === false) request.sparkline = false;
      if (config.period && ['day', 'week', 'month', 'year'].includes(config.period)) request.range = config.period;
      if (Number(config.offset) < 0) request.offset = Math.max(-60, Math.round(Number(config.offset)));
      // Optional: die Datumsauswahl der Energie von Home Assistant. Sie steht nur zur Verfügung, wenn schon eine Energie-Ansicht sie
      // angelegt hat (hass.connection._energy); sonst gilt der feste Zeitraum der Karte.
      const energy = config.follow_energy_date ? this._energyPeriod() : null;
      if (energy) { request.range = energy.range; request.offset = energy.offset; }
      if (config.years != null) request.years = Number(config.years);
      if (config.mode === 'komplett') request.mode = 'komplett';
      if (config.limit != null) request.limit = Number(config.limit);
      return request;
    }
    if (config.table_id && !config.chart_id) return {type: 'zeitarchiv/card/table', table_id: config.table_id};
    const request = {type: 'zeitarchiv/card/chart', chart_id: config.chart_id, px};
    if (PERIODS.includes(config.period)) request.period = config.period;
    return request;
  }

  // Zeitraum der Datumsauswahl der Energie von Home Assistant als Bereich und Versatz in Perioden zurück, oder null.
  // HA legt die Sammlung erst an, wenn eine Energie-Ansicht sie braucht; ihr Aufbau ist nicht dokumentiert (die Quelle nennt
  // den Zugriff von Karten ausdrücklich), darum jeder Zugriff abgesichert.
  _energyPeriod() {
    try {
      const collection = this._hass?.connection?._energy;
      const start = collection?.start;
      if (!(start instanceof Date)) return null;
      const end = collection.end instanceof Date ? collection.end : new Date();
      const days = (end - start) / 864e5;
      const now = new Date();
      const day = (date) => Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
      let range;
      let offset;
      if (days <= 1.5) { range = 'day'; offset = Math.round((day(start) - day(now)) / 864e5); }
      else if (days <= 8) {
        // Wochenanfang der laufenden Woche mit demselben Wochentag wie der gewählte Start vergleichen,
        // sonst rundet eine rohe Tagesdifferenz ab dem vierten Wochentag auf die falsche Woche.
        range = 'week';
        const thisWeek = day(now) - ((now.getDay() - start.getDay() + 7) % 7) * 864e5;
        offset = Math.round((day(start) - thisWeek) / (7 * 864e5));
      }
      else if (days <= 32) { range = 'month'; offset = (start.getFullYear() - now.getFullYear()) * 12 + start.getMonth() - now.getMonth(); }
      else if (days <= 370) { range = 'year'; offset = start.getFullYear() - now.getFullYear(); }
      else return null;
      return {range, offset: Math.max(-60, Math.min(0, offset))};
    } catch (err) {
      return null;
    }
  }

  // Wechselt die Datumsauswahl, lädt die Karte neu; abgemeldet wird beim Entfernen der Karte.
  _followEnergy() {
    this._unfollow?.();
    this._unfollow = null;
    const collection = this._hass?.connection?._energy;
    if (!this._config?.follow_energy_date || typeof collection?.subscribe !== 'function') return;
    try {
      let first = true;
      const stop = collection.subscribe(() => {
        if (first) { first = false; return; }
        this._load();
      });
      this._unfollow = typeof stop === 'function' ? stop : null;
    } catch (err) {
      this._unfollow = null;
    }
  }

  _stale() {
    return Date.now() - this._lastGood > Math.max(15, Number(this._config?.refresh) || 60) * 1000;
  }

  _schedule() {
    clearTimeout(this._timer);
    if (!this.isConnected) return;
    this._timer = setTimeout(() => {
      if (!document.hidden && this._visible) this._load();
      else this._schedule();
    }, retryDelaySeconds(this._failures, this._config?.refresh) * 1000);
  }

  _showNote(key, error = false) {
    const note = this._els.note;
    note.textContent = text(this._hass, key);
    note.className = error ? 'note error' : 'note';
    note.setAttribute('role', error ? 'alert' : 'status');
    note.hidden = false;
    this._els.chart.hidden = true;
    this._els.legend.hidden = true;
    this._els.table.hidden = true;
    this._shown = false;
  }

  _setHeader(name) {
    const title = this._config.title || name;
    this._els.header.textContent = title || '';
    this._els.header.hidden = !title;
  }

  async _load() {
    if (!this._config || !this._hass) return;
    // Läuft schon eine Anfrage (alte Konfiguration), wird danach sofort neu geladen, statt ihr Ergebnis
    // bis zur nächsten Aktualisierung stehen zu lassen.
    if (this._loading) { this._reload = true; return; }
    if (!this._hasSource()) { this._showNote('chooseChart'); return; }
    this._loading = true;
    const generation = this._generation;
    try {
      const result = await this._hass.callWS(this._request());
      if (generation === this._generation) {
        await this._draw(result);
        this._lastGood = Date.now();
        this._failures = 0;
        this._els.badge.hidden = true;
      }
    } catch (err) {
      if (generation === this._generation) {
        this._failures += 1;
        this._fail(err);
      }
    } finally {
      this._loading = false;
      if (this._reload || generation !== this._generation) {
        this._reload = false;
        this._load();
      } else {
        this._schedule();
      }
    }
  }

  _fail(err) {
    let key = err && typeof err === 'object' && err.code && TEXTS.en[err.code] ? err.code : (err && err.script ? 'script' : 'unknown');
    // Bausteine sind nur für Administratoren; „Karte freigeben“ gilt für Charts und Tabellen und würde hier in die Irre führen.
    if (key === 'unauthorized' && this._config?.element) key = 'elementAdminOnly';
    if (key !== 'unknown' && key !== 'script' && err.code !== 'unauthorized') console.debug('Zeitarchiv-Karte:', err.code, err.message);
    else console.warn('Zeitarchiv-Karte:', err);
    // Ein Ausfall nach einem guten Stand lässt das Bild stehen und sagt nur, wie alt es ist.
    if (this._shown && this._lastGood && ['unreachable', 'busy', 'auth_failed', 'too_large', 'app_error'].includes(key)) {
      this._els.badge.textContent = text(this._hass, key === 'app_error' ? 'staleError' : 'stale', {min: Math.max(1, Math.round((Date.now() - this._lastGood) / 60000))});
      this._els.badge.hidden = false;
      return;
    }
    this._showNote(key, true);
  }

  async _draw(result) {
    if (!result || result.spec_version !== SPEC_VERSION) { const err = new Error('spec_version'); err.code = 'spec'; throw err; }
    this._setHeader(result.name);
    if (result.renderer) { await this._drawElement(result); return; }
    if (result.table) { await this._drawTable(result); return; }
    this._els.table.hidden = true;
    this._els.legend.hidden = true;
    if (!result.supported || !result.data) {
      this._showNote('unsupported');
      return;
    }
    let runtime;
    try {
      runtime = await runtimeFor({
        timezone: result.env?.timezone || 'UTC',
        language: this._hass.locale?.language || this._hass.language || 'en',
        dark: Boolean(this._hass.themes?.darkMode),
      });
    } catch (err) {
      err.script = true;
      throw err;
    }
    // Wurde die Karte entfernt, während die Quellen luden: sonst legte echarts.init() an dem abgelösten Element eine
    // Instanz an, die nie freigegeben wird (ECharts hält sie in seiner globalen Liste).
    if (!this.isConnected) return;
    const R = runtime.render;
    const spec = R.readSpec(result.spec);
    const series = R.prepareSeries(result.data);
    if (!R.hasData(series)) { this._showNote('noData'); return; }
    this._els.note.hidden = true;
    this._els.chart.hidden = false;
    if (!this._chart) this._chart = runtime.echarts.init(this._els.chart);
    const vars = this._themeVars();
    runtime.setVars(vars);
    const style = {getPropertyValue: (name) => vars[name] ?? ''};
    // Langzeit-Vergleich (ein Jahr, eine Entität): Monate je Jahr statt einer Zeitachse, wie auf der Kachel.
    const multiYear = spec.compare?.longterm && series.length === 1 && Array.isArray(series[0].years)
      ? R.tileMultiYear(series[0], result.data, spec.compare, {
        small: false, color: spec.colorFor(series[0].entity_id), inkMuted: style.getPropertyValue('--ink-muted').trim(),
      })
      : null;
    R.draw(this._chart, {
      spec, data: result.data, series, viewType: R.viewTypeFor(spec, series), multiYear, hiddenSet: this._hidden, style,
    });
    this._renderLegend(runtime, result, spec, series, multiYear);
    this._els.chart.setAttribute('aria-label', this._describe(this._config.title || result.name, series, result.spec));
    this._applyAction();
    this._chart.resize();
    this._shown = true;
  }

  // Legende mit Werten (Roadmap 1.49): dieselbe Datei und dieselben Klassen wie auf der Kachel der App.
  // Sie gilt, wenn die App die Legenden-Einstellungen des Charts mitschickt (spec.chartStats) und dort Werte
  // an sind; sonst, bei einer älteren App, ohne Werte, beim Donut und bei "legend: false" bleibt die Namensliste.
  // Einstellbar an der Karte: legend_style ('' = wie das Chart, 'chips', 'table') und legend_metrics (leer = wie das Chart).
  _renderLegend(runtime, result, spec, series, multiYear) {
    const raw = result.spec || {};
    const donut = (this._chart.getOption().series || []).some((entry) => entry.type === 'pie');
    // "Aus" (an der Karte oder im Chart) blendet die Legende ganz aus, auch die Namensliste.
    if ((this._config.legend_style || raw.legendStyle) === 'off') { this._hideLegend(); return; }
    if (raw.chartStats !== 'true' || donut || this._config.legend === false) { this._renderNameLegend(); return; }
    const box = this._els.legend;
    let metrics = [];
    try { metrics = JSON.parse(raw.legendMetrics || '[]'); } catch (err) { /* ohne */ }
    const own = Array.isArray(this._config.legend_metrics) ? this._config.legend_metrics.filter((key) => LEGEND_KEYS.includes(key)) : [];
    if (own.length) metrics = own;
    // Die Chips und die Tabelle der Legende tragen die Klassen der App; ihr Aussehen steht in table.css, das bisher nur
    // Tabellen und Bausteine luden. Ein Chart allein zeigte die Legende darum ohne Abstände und Rahmen.
    if (this._els.tableCss.textContent !== runtime.tableCss) this._els.tableCss.textContent = runtime.tableCss;
    this._chartLegendStyle = raw.legendStyle || 'chips';
    const style = this._legendStyle(this._chartLegendStyle);
    this._legend = {
      items: runtime.LegendRender.buildLegendItems({series, data: result.data, spec, multiYear}),
      legendMetrics: Array.isArray(metrics) ? metrics : [], showStats: true, style,
    };
    this._legendRender = runtime.LegendRender;
    box.className = 'legend values dtile-legend is-visible';
    // Größe: eigene Option, sonst die des Charts, sonst Normal (die globale Einstellung der App kennt die Karte nicht).
    box.dataset.legendSize = this._config.legend_size || raw.legendSize || 'normal';
    box.hidden = false;
    this._paintLegend();
  }

  _hideLegend() {
    const box = this._els.legend;
    box.replaceChildren();
    box.className = 'legend';
    box.hidden = true;
    this._legend = null;
  }

  // "Wie das Chart" ist auf einer schmalen Karte (unter etwa 300 px) eine Chip-Reihe: eine Tabelle würde seitlich
  // scrollen. Wer "Tabelle" ausdrücklich wählt, behält sie.
  _legendStyle(chartStyle) {
    if (this._config.legend_style) return this._config.legend_style;
    const narrow = (this._els.card?.clientWidth || 1000) < NARROW_CARD_PX;
    return chartStyle === 'table' && narrow ? 'chips' : chartStyle;
  }

  // Ändert sich die Breite der Karte (Telefon gedreht, andere Spaltenzahl), gilt die Regel oben neu.
  _restyleLegend() {
    if (!this._legend || !this._legendRender || !this._els.legend.classList.contains('values')) return;
    const style = this._legendStyle(this._chartLegendStyle);
    if (style === this._legend.style) return;
    this._legend.style = style;
    this._paintLegend();
  }

  _paintLegend() {
    if (!this._legend) return;
    this._els.legend.innerHTML = this._legendRender.renderLegendHtml(this._legend, this._hidden);
  }

  // Ein Klick-Verteiler für die ganze Legende (Chips und Tabellenzeilen), wie auf der Kachel: blendet die Serie
  // ein oder aus und löst die tap_action der Karte nicht aus.
  _wireLegend() {
    const box = this._els.legend;
    const toggle = (event) => {
      if (!box.classList.contains('values')) return;
      event.stopPropagation();
      const item = event.target.closest?.('[data-series]');
      if (!item || !box.contains(item)) return;
      if (event.type === 'keydown') {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
      }
      const name = item.dataset.series;
      if (this._hidden.has(name)) this._hidden.delete(name); else this._hidden.add(name);
      this._chart?.dispatchAction({type: 'legendToggleSelect', name});
      this._paintLegend();
      // Die Legende wird neu aufgebaut; per Tastatur bedient, würde der Fokus sonst auf den Seitenanfang springen.
      if (event.type === 'keydown') [...box.querySelectorAll('[data-series]')].find((el) => el.dataset.series === name)?.focus();
    };
    box.addEventListener('click', toggle);
    box.addEventListener('keydown', toggle);
  }

  // Legende unter dem Chart: ein Eintrag je Serie (Name und Farbe wie im Chart), ein Klick blendet die Serie
  // ein oder aus. Bei nur einer Serie und beim Donut entfällt sie (Titel bzw. Beschriftung nennen alles).
  _renderNameLegend() {
    const box = this._els.legend;
    box.replaceChildren();
    box.className = 'legend';
    this._legend = null;
    const option = this._chart.getOption();
    const series = option.series || [];
    const names = [];
    (option.legend?.[0]?.data || []).forEach((entry) => {
      const name = typeof entry === 'string' ? entry : entry?.name;
      if (name && !names.includes(name)) names.push(name);
    });
    const donut = series.some((entry) => entry.type === 'pie');
    // Eine einzelne Serie braucht von sich aus keine Legende; wer "Legende anzeigen" ausdrücklich
    // einschaltet (legend: true), bekommt sie trotzdem.
    box.hidden = this._config.legend === false || donut || names.length < (this._config.legend === true ? 1 : 2);
    if (box.hidden) return;
    names.forEach((name) => {
      const index = series.findIndex((entry) => entry.name === name);
      const item = document.createElement('button');
      item.type = 'button';
      item.className = `legend-item${this._hidden.has(name) ? ' inactive' : ''}`;
      const dot = document.createElement('span');
      dot.className = 'legend-dot';
      dot.style.background = (index >= 0 && this._chart.getVisual({seriesIndex: index}, 'color')) || 'var(--primary-color)';
      item.append(dot, document.createTextNode(name));
      item.addEventListener('click', (event) => {
        // Kein Auslösen der tap_action der Karte.
        event.stopPropagation();
        if (this._hidden.has(name)) this._hidden.delete(name); else this._hidden.add(name);
        item.classList.toggle('inactive', this._hidden.has(name));
        this._chart.dispatchAction({type: 'legendToggleSelect', name});
      });
      box.appendChild(item);
    });
  }

  // Text für Screenreader: das Chart ist ein Bild (Canvas), also nennt der Name zu jeder Serie ihren Wert, bei
  // Zählern die Summe, sonst den letzten. Serien ohne Zahlenwerte (Zustände, Heatmap) erscheinen nur mit Namen.
  _describe(title, series, spec) {
    const language = this._hass.locale?.language || this._hass.language || 'en';
    let hidden = [];
    let names = {};
    try { hidden = JSON.parse(spec?.hiddenEntityIds || '[]'); names = JSON.parse(spec?.entityNames || '{}'); } catch (err) { /* ohne */ }
    // Gültiges JSON mit anderem Typ ("null", Zahl) darf das Chart nicht in den Fehlerzustand werfen.
    if (!Array.isArray(hidden)) hidden = [];
    if (!names || typeof names !== 'object' || Array.isArray(names)) names = {};
    const parts = series.filter((s) => !hidden.includes(s.entity_id)).map((s) => {
      const name = names[s.entity_id] || s.friendly_name || s.entity_id;
      const values = (s.points || []).map((point) => point.value).filter(Number.isFinite);
      if (!values.length) return name;
      const counter = s.aggregation_type === 'counter';
      const value = counter ? values.reduce((a, b) => a + b, 0) : values[values.length - 1];
      const digits = Number.isInteger(s.decimals) ? s.decimals : 2;
      const shown = new Intl.NumberFormat(language, {maximumFractionDigits: digits}).format(value);
      return `${name}: ${text(this._hass, counter ? 'sum' : 'last')} ${shown}${s.unit ? ` ${s.unit}` : ''}`;
    });
    const shownParts = parts.slice(0, 8);
    if (parts.length > 8) shownParts.push(text(this._hass, 'more', {n: parts.length - 8}));
    return `${text(this._hass, 'chartLabel', {title: title || ''})}. ${shownParts.join('; ')}`;
  }

  // Gespeicherte Tabelle: dieselben Dateien wie die Tabellen-Kachel der App rechnen die Zellen aus der fertigen
  // Antwort des Servers und bauen das HTML; table.css liefert das Aussehen.
  async _drawTable(result) {
    let runtime;
    try {
      runtime = await runtimeFor({
        timezone: result.env?.timezone || 'UTC',
        language: this._hass.locale?.language || this._hass.language || 'en',
        dark: Boolean(this._hass.themes?.darkMode),
      });
    } catch (err) {
      err.script = true;
      throw err;
    }
    const {TableTileRender} = runtime.tables;
    const table = await TableTileRender.compute(result.table.columns, result.table.rows, {queryTable: async () => result.query});
    if (!this.isConnected) return;
    if (table.empty) { this._showNote('noVisible'); return; }
    if (this._els.tableCss.textContent !== runtime.tableCss) this._els.tableCss.textContent = runtime.tableCss;
    this._els.note.hidden = true;
    this._els.chart.hidden = true;
    this._els.chart.removeAttribute('aria-label');
    this._els.legend.hidden = true;
    this._els.table.hidden = false;
    this._els.table.style.maxHeight = this._explicitHeight ? `${Math.max(120, Number(this._config.height) || 260)}px` : '';
    this._els.table.innerHTML = TableTileRender.buildHtml({...table, style: result.table.style || {}});
    TableTileRender.afterInsert(this._els.table);
    this._applyAction();
    this._shown = true;
  }

  // Dashboard-Baustein (Roadmap 1.48): die App liefert die Zahlen des Dashboards, gezeichnet wird mit derselben
  // Datei (element-table-render.js) wie im Dashboard der App.
  async _drawElement(result) {
    let runtime;
    try {
      runtime = await runtimeFor({
        timezone: result.env?.timezone || 'UTC',
        language: this._hass.locale?.language || this._hass.language || 'en',
        dark: Boolean(this._hass.themes?.darkMode),
      });
    } catch (err) {
      err.script = true;
      throw err;
    }
    if (!this.isConnected) return;
    if (result.kind === 'chart') { this._drawElementChart(result, runtime); return; }
    if (result.kind === 'kpi') { this._drawElementKpi(result, runtime); return; }
    // Die Farben der Matrix sind CSS-Ausdrücke: sie stehen in style="…" und lösen sich im Thema von Home Assistant auf.
    const colors = {good: 'var(--success-color, #43a047)', bad: 'var(--error-color, #db4437)', base: 'var(--secondary-background-color, #f5f5f5)'};
    const draw = {
      'energie.zeitraeume': (R) => `<table class="dt wt-table">${R.energyComparison(result.table, this._config.diff !== false)}</table>`,
      'wetter.zeitraeume': (R) => `<table class="dt wt-table">${R.weatherComparison(result.table, result.group || 'basis', this._config.diff !== false)}</table>`,
      'energie.matrix': (R) => `<table class="dt wt-tm">${R.energyMatrix(result.months, result.months.roles[0], {colors, href: () => ''})}</table>`,
      'energie.kenntage': (R) => R.energyKenntageBlock(result.kenntage, result.ytd),
      'energie.veraenderungen': (R) => R.energyChangesBlock(result.changes),
    }[result.renderer];
    if (!draw) { this._showNote('elementsOutdated'); return; }
    if (this._els.tableCss.textContent !== runtime.tableCss) this._els.tableCss.textContent = runtime.tableCss;
    this._els.note.hidden = true;
    this._els.chart.hidden = true;
    this._els.chart.removeAttribute('aria-label');
    this._els.legend.hidden = true;
    this._els.table.hidden = false;
    this._els.table.style.maxHeight = this._explicitHeight ? `${Math.max(120, Number(this._config.height) || 260)}px` : '';
    this._els.table.innerHTML = draw(runtime.ElementTableRender);
    this._applyAction();
    this._shown = true;
  }

  // Kennzahlen-Baustein (Roadmap 1.48, P3): Kacheln mit Wert, Vorperiode und Verlauf.
  _drawElementKpi(result, runtime) {
    const R = runtime.ElementKpiRender;
    const html = {
      'energie.kennzahlen': () => R.energyKpis(result.items, {compareLabel: result.compare_label}),
      'wetter.kennzahlen': () => R.weatherKpis(result.tiles),
      'energie.rekorde': () => R.energyRecords(result),
      'energie.speicher': () => R.energyStorage(result),
    }[result.renderer];
    if (!html) { this._showNote('elementsOutdated'); return; }
    this._els.note.hidden = true;
    this._els.chart.hidden = true;
    this._els.chart.removeAttribute('aria-label');
    this._els.legend.hidden = true;
    this._els.table.hidden = false;
    this._els.table.style.maxHeight = this._explicitHeight ? `${Math.max(120, Number(this._config.height) || 260)}px` : '';
    this._els.table.innerHTML = html();
    this._applyAction();
    this._shown = true;
  }

  // Diagramm-Baustein: die App liefert die Zahlen, element-chart-render.js die ECharts-Optionen (dieselben wie im Dashboard).
  _drawElementChart(result, runtime) {
    const make = {
      'energie.monatsvergleich': (R, colors, extra) => R.energyMonthly(result.months, result.months.roles[0], {colors, ...extra}),
      'wetter.monatsvergleich': (R, colors, extra) => R.weatherMonthly(result.monthly, {colors, ...extra}),
      'wetter.matrix': (R, colors, extra) => R.weatherMatrix(result.matrix, {colors, ...extra}),
      'energie.anteile': (R, colors, extra, palette) => R.energyShares(result.items, {colorAt: (index) => palette[index % palette.length], surface: colors.surface}),
      'energie.heatmap': (R, colors, extra) => (result.heatmap.rows?.length
        ? R.energyHeatmap(result.heatmap, {colors: {ink: colors.ink, accent: colors.cur, surfaceAlt: vars['--surface-alt'], surface: colors.surface, mono: vars['--font-mono']}, font: extra.font})
        : null),
    }[result.renderer];
    if (!make) { this._showNote('elementsOutdated'); return; }
    const vars = this._themeVars();
    runtime.setVars(vars);
    const palette = this._hass.themes?.darkMode ? PALETTES.dark : PALETTES.light;
    // ECharts versteht kein color-mix(): die Töne der Sonnenklassen werden hier gemischt.
    const mix = (a, b, share) => {
      const parse = (value) => {
        const hex = /^#([0-9a-f]{6})$/i.exec(String(value).trim());
        if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16));
        const rgb = /rgba?\(([^)]+)\)/.exec(String(value));
        return rgb ? rgb[1].split(',').slice(0, 3).map((n) => Number(n)) : [255, 255, 255];
      };
      const [x, y] = [parse(a), parse(b)];
      return `rgb(${x.map((v, i) => Math.round(v * share + y[i] * (1 - share))).join(',')})`;
    };
    const colors = {
      cur: palette[0], prev: palette[1], cold: palette[2], text: vars['--ink-faint'], faint: vars['--ink-faint'], grid: vars['--border'],
      ink: vars['--ink'], surface: vars['--surface'],
      sun: mix(palette[6], vars['--surface'], 0.7), sunSoft: mix(palette[6], vars['--surface'], 0.3), overcast: mix(vars['--ink-faint'], vars['--surface'], 0.4),
    };
    this._els.note.hidden = true;
    this._els.table.hidden = true;
    this._els.legend.hidden = true;
    this._els.chart.hidden = false;
    if (!this._chart) this._chart = runtime.echarts.init(this._els.chart);
    const option = make(runtime.ElementChartRender, colors, {band: this._config.band !== false, narrow: this._els.chart.clientWidth < 520}, palette);
    if (!option) { this._showNote('noData'); return; }
    this._chart.setOption(option, true);
    this._els.chart.setAttribute('aria-label', `${this._config.title || result.title || ''}`);
    this._applyAction();
    this._chart.resize();
    this._shown = true;
  }

  // Die Farben, die die Zeichenregeln aus dem CSS der App lesen, aus dem Thema von Home Assistant.
  _themeVars() {
    const css = getComputedStyle(this);
    const get = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    return {
      '--border': get('--divider-color', '#e0e0e0'),
      '--ink-faint': get('--secondary-text-color', '#727272'),
      '--ink': get('--primary-text-color', '#212121'),
      '--ink-muted': get('--primary-text-color', '#212121'),
      '--surface-alt': get('--secondary-background-color', '#f5f5f5'),
      '--surface': get('--card-background-color', '#ffffff'),
      '--font-mono': get('--ha-font-family-body', 'Roboto, sans-serif'),
    };
  }
}

// --- Editor ----------------------------------------------------------------------------

class ZeitarchivCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._items = null;
    this._tables = [];
    this._elements = null;
    this._entities = null;
    this._source = 'chart';
    this._error = null;
    this._form = null;
  }

  setConfig(config) {
    this._config = config || {};
    const pickedEntities = Array.isArray(this._config.entities) && this._config.entities.length;
    if (pickedEntities) this._source = 'entities';
    else if (this._config.element) this._source = 'element';
    else if (this._config.table_id && !this._config.chart_id) this._source = 'table';
    else if (this._config.chart_id) this._source = 'chart';
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    if (first) this._load();
  }

  _failure(err) {
    return err && err.code && TEXTS.en[err.code] ? text(this._hass, err.code) : text(this._hass, 'unknown');
  }

  async _load() {
    try {
      const listed = await this._hass.callWS({type: 'zeitarchiv/card/items'});
      this._items = listed.items || [];
      this._tables = listed.tables || [];
    } catch (err) {
      this._items = [];
      this._error = this._failure(err);
    }
    this._render();
  }

  async _loadEntities() {
    if (this._entities) return;
    this._entities = [];
    try {
      this._entities = (await this._hass.callWS({type: 'zeitarchiv/card/entities'})).entities || [];
    } catch (err) {
      this._error = this._failure(err);
    }
    this._render();
  }

  async _loadElements() {
    if (this._elements) return;
    this._elements = [];
    try {
      this._elements = (await this._hass.callWS({type: 'zeitarchiv/card/elements'})).elements || [];
    } catch (err) {
      this._error = this._failure(err);
    }
    this._render();
  }

  _schema() {
    const label = (key) => text(this._hass, key);
    const chartOptions = (this._items || []).map((item) => ({
      value: String(item.id),
      label: item.supported ? item.name : `${item.name} (${label('notSupportedShort')})`,
    }));
    const select = (name, options) => ({name, selector: {select: {mode: 'dropdown', options}}});
    const tableOptions = this._tables.map((item) => ({value: String(item.id), label: item.name}));
    const schema = [select('source', [
      {value: 'chart', label: label('sourceChart')}, {value: 'table', label: label('sourceTable')},
      {value: 'element', label: label('sourceElement')}, {value: 'entities', label: label('sourceEntities')},
    ])];
    if (this._source === 'entities') {
      schema.push(
        // Die gewählten Entitäten gehören immer in die Liste: beim Wiederöffnen ist die Liste des Servers noch
        // nicht da, und der Picker meldete sie sonst als "Unbekannte Entität".
        {name: 'entities', required: true, selector: {entity: {multiple: true, include_entities: [...new Set([
          ...(this._config.entities || []), ...(this._entities || []).map((e) => e.entity_id)])]}}},
        select('period', PERIODS.map((value) => ({value, label: label(`period_${value}`)}))),
        select('style', ['auto', 'stacked', 'percent'].map((value) => ({value, label: label(`style_${value}`)}))),
      );
    } else if (this._source === 'element') {
      // Die gewählte Fassung gehört immer in die Liste, auch solange die der App noch lädt.
      const listed = this._elements || [];
      const current = this._config.element;
      const options = listed.map((item) => ({value: item.key, label: item.title}));
      if (current && !listed.some((item) => item.key === current)) options.push({value: current, label: current});
      schema.push({...select('element', options), required: true});
      const chosen = listed.find((item) => item.key === current);
      if (chosen && chosen.roles && chosen.roles.length) {
        schema.push(select('role', chosen.roles.map((value) => ({value, label: label(`role_${value}`)}))));
      }
      if (chosen && ((chosen.roles && chosen.roles.length) || chosen.year_limit)) {
        schema.push(select('years', ['5', '10', '0'].map((value) => ({value, label: label(`years_${value}`)}))));
      }
      if (chosen && chosen.modes) schema.push(select('mode', ['bis_jetzt', 'komplett'].map((value) => ({value, label: label(`mode_${value}`)}))));
      if (chosen && chosen.limit) schema.push({name: 'limit', selector: {number: {min: 1, max: 20, step: 1, mode: 'box'}}});
      if (chosen && chosen.metrics && chosen.metrics.length) {
        schema.push(select('metric', chosen.metrics.map((value) => ({value, label: label(`metric_${value}`)}))));
      }
      if (chosen && /monatsvergleich$/.test(chosen.key)) schema.push({name: 'band', selector: {boolean: {}}});
      if (chosen && chosen.values && chosen.values.length) {
        schema.push({name: 'values', selector: {select: {multiple: true, mode: 'list', options: chosen.values.map((item) => ({value: item.key, label: item.label || label(`role_${item.key}`)}))}}});
      }
      if (chosen && ['energie.kennzahlen', 'energie.speicher'].includes(chosen.key)) schema.push({name: 'sparkline', selector: {boolean: {}}});
      if (chosen && chosen.sides && chosen.sides.length) {
        schema.push(select('side', chosen.sides.map((value) => ({value, label: label(`side_${value}`)}))));
      }
      if (chosen && chosen.ranges && chosen.ranges.length) {
        // Zeitraum, Versatz und die Datumsauswahl gehören zusammen und stehen in einem eigenen, offenen Abschnitt.
        schema.push({
          type: 'expandable', name: '', title: label('period_group'), expanded: true,
          schema: [
            select('period', chosen.ranges.map((value) => ({value, label: label(`period_${value}`)}))),
            {name: 'offset', selector: {number: {min: -60, max: 0, step: 1, mode: 'box'}}},
            {name: 'follow_energy_date', selector: {boolean: {}}},
          ],
        });
      }
      if (chosen && chosen.groups && chosen.groups.length) {
        schema.push(select('group', chosen.groups.map((value) => ({value, label: label(`group_${value}`)}))));
      }
      if (chosen && chosen.columns && chosen.columns.length) {
        schema.push(
          {name: 'columns', selector: {select: {multiple: true, mode: 'list', options: chosen.columns.map((value) => ({value, label: label(`column_${value}`)}))}}},
          {name: 'vorjahr', selector: {boolean: {}}},
          {name: 'diff', selector: {boolean: {}}},
        );
      }
    } else if (this._source === 'table') {
      schema.push({...select('table_id', tableOptions), required: true});
    } else {
      schema.push(
        {...select('chart_id', chartOptions), required: true},
        select('period', ['saved', ...PERIODS].map((value) => ({value, label: label(`period_${value}`)}))),
      );
    }
    if (this._source !== 'table' && this._source !== 'element') {
      schema.push({name: 'legend', selector: {boolean: {}}});
      // Stil und Kennzahlen der Legende mit Werten (Roadmap 1.49); leer = wie im Chart.
      if (this._config.legend !== false) {
        // Der Schalter bleibt sichtbar; Stil und Kennzahlen stehen eingeklappt, offen, sobald etwas gewählt ist.
        schema.push({
          type: 'expandable', name: '', title: label('legend_more'),
          expanded: Boolean(this._config.legend_style || this._config.legend_size || (this._config.legend_metrics || []).length),
          schema: [
            select('legend_style', ['chart', 'chips', 'table', 'off'].map((value) => ({value, label: label(`legendStyle_${value}`)}))),
            select('legend_size', ['chart', 'normal', 'small'].map((value) => ({value, label: label(`legendSize_${value}`)}))),
            {name: 'legend_metrics', selector: {select: {multiple: true, mode: 'list', options: LEGEND_KEYS.map((value) => ({value, label: label(`metric_${value}`)}))}}},
          ],
        });
      }
    }
    // Der Titel bleibt sichtbar; Aktualisierung, Höhe und Tippen sind selten nötig und stehen eingeklappt.
    schema.push(
      {name: 'title', selector: {text: {}}},
      {
        type: 'expandable', name: '', title: label('moreSettings'),
        schema: [
          {name: 'refresh', selector: {number: {min: 15, max: 3600, step: 15, mode: 'box', unit_of_measurement: 's'}}},
          {name: 'height', selector: {number: {min: 120, max: 800, step: 10, mode: 'box', unit_of_measurement: 'px'}}},
          {name: 'tap_action', selector: {ui_action: {default_action: 'none'}}},
        ],
      },
    );
    return schema;
  }

  _data() {
    const data = {...this._config, source: this._source};
    if (data.chart_id != null) data.chart_id = String(data.chart_id);
    if (data.table_id != null) data.table_id = String(data.table_id);
    if (this._source === 'entities') {
      data.period = data.period || 'month';
      data.style = data.style || 'auto';
    } else if (this._source === 'chart') {
      data.period = data.period || 'saved';
    }
    data.legend = data.legend !== false;
    data.legend_style = data.legend_style || 'chart';
    data.legend_size = data.legend_size || 'chart';
    data.legend_metrics = Array.isArray(data.legend_metrics) ? data.legend_metrics : [];
    if (this._source === 'element') {
      const chosen = (this._elements || []).find((item) => item.key === data.element);
      data.columns = Array.isArray(data.columns) && data.columns.length ? data.columns : (chosen?.columns || []);
      data.vorjahr = data.vorjahr !== false;
      data.diff = data.diff !== false;
      if (chosen?.groups?.length) data.group = data.group || chosen.groups[0];
      if (chosen?.metrics?.length) data.metric = data.metric || chosen.metrics[0];
      if (chosen?.values?.length) {
        data.values = Array.isArray(data.values) && data.values.length ? data.values : chosen.values.filter((item) => item.default).map((item) => item.key);
        if (chosen.key === 'energie.kennzahlen') data.sparkline = data.sparkline !== false;
      }
      if (chosen?.key === 'energie.speicher') data.sparkline = data.sparkline !== false;
      if (chosen?.sides?.length) data.side = data.side || chosen.sides[0];
      if (chosen?.ranges?.length) {
        data.period = chosen.ranges.includes(data.period) ? data.period : (chosen.ranges.includes('month') ? 'month' : chosen.ranges[0]);
        data.offset = Number(data.offset) || 0;
        data.follow_energy_date = Boolean(data.follow_energy_date);
      }
      if (chosen && /monatsvergleich$/.test(chosen.key)) data.band = data.band !== false;
      if (chosen?.roles?.length) data.role = data.role || chosen.roles[0];
      if (chosen?.roles?.length || chosen?.year_limit) data.years = String(data.years ?? 10);
      if (chosen?.modes) data.mode = data.mode === 'komplett' ? 'komplett' : 'bis_jetzt';
      if (chosen?.limit) data.limit = Number(data.limit) || 8;
    }
    return data;
  }

  _changed(value) {
    const next = {...value};
    const source = next.source || this._source;
    delete next.source;
    if (source !== this._source) {
      this._source = source;
      delete next.chart_id; delete next.table_id; delete next.entities; delete next.period; delete next.style; delete next.legend;
      delete next.legend_style; delete next.legend_size; delete next.legend_metrics;
      delete next.element; delete next.columns; delete next.vorjahr; delete next.diff; delete next.role; delete next.years; delete next.group; delete next.metric; delete next.band; delete next.side; delete next.offset; delete next.follow_energy_date; delete next.values; delete next.sparkline; delete next.mode; delete next.limit;
      if (source === 'entities') this._loadEntities();
      if (source === 'element') this._loadElements();
    }
    for (const key of ['chart_id', 'table_id']) {
      if (next[key] !== undefined && next[key] !== '') next[key] = Number(next[key]);
      else delete next[key];
    }
    if (!next.title) delete next.title;
    if (!next.tap_action || !next.tap_action.action || next.tap_action.action === 'none') delete next.tap_action;
    if (this._source !== 'entities') for (const key of ['entities', 'style']) delete next[key];
    if (this._source === 'table' || next.period === 'saved') delete next.period;
    if (next.legend !== false) delete next.legend;
    // Vorgaben nicht in die YAML schreiben: "wie im Chart" ist kein Stil und keine Auswahl.
    if (!['chips', 'table', 'off'].includes(next.legend_style) || next.legend === false || ['table', 'element'].includes(this._source)) delete next.legend_style;
    if (!['normal', 'small'].includes(next.legend_size) || next.legend === false || ['table', 'element'].includes(this._source)) delete next.legend_size;
    if (!Array.isArray(next.legend_metrics) || !next.legend_metrics.length || next.legend === false || ['table', 'element'].includes(this._source)) delete next.legend_metrics;
    if (this._source !== 'chart') delete next.chart_id;
    if (this._source !== 'table') delete next.table_id;
    if (this._source !== 'element') for (const key of ['element', 'columns', 'vorjahr', 'diff', 'role', 'years', 'group', 'metric', 'band', 'side', 'offset', 'follow_energy_date', 'values', 'sparkline', 'mode', 'limit']) delete next[key];
    else {
      // Vorgaben nicht in die YAML schreiben: alle Spalten, mit Vorjahr, mit Differenz.
      const all = (this._elements || []).find((item) => item.key === next.element)?.columns || [];
      if (!Array.isArray(next.columns) || !next.columns.length || (next.columns.length === all.length && all.every((c) => next.columns.includes(c)))) delete next.columns;
      if (next.vorjahr !== false) delete next.vorjahr;
      if (next.diff !== false) delete next.diff;
      // Fehlt die Elementliste noch (nicht geladen oder fehlgeschlagen) oder kennt sie das Element nicht, bleiben die Optionen
      // stehen: ohne Katalog wüsste die Bereinigung nicht, was Vorgabe ist, und würde Zeitraum, Rolle, Werte u. a. löschen.
      const known = (this._elements || []).some((item) => item.key === next.element);
      if (next.years !== undefined && next.years !== '') next.years = Number(next.years); else delete next.years;
      if (known) {
        const chosenRoles = (this._elements || []).find((item) => item.key === next.element)?.roles || [];
        if (!chosenRoles.length || next.role === chosenRoles[0]) delete next.role;
        const chosenForYears = (this._elements || []).find((item) => item.key === next.element);
        if (!(chosenRoles.length || chosenForYears?.year_limit) || next.years === 10) delete next.years;
        if (!chosenForYears?.modes || next.mode !== 'komplett') delete next.mode;
        if (!chosenForYears?.limit || Number(next.limit) === 8 || !Number(next.limit)) delete next.limit; else next.limit = Math.max(1, Math.min(20, Math.round(Number(next.limit))));
        const chosenGroups = (this._elements || []).find((item) => item.key === next.element)?.groups || [];
        if (!chosenGroups.length || next.group === chosenGroups[0]) delete next.group;
        const chosenMetrics = (this._elements || []).find((item) => item.key === next.element)?.metrics || [];
        if (!chosenMetrics.length || next.metric === chosenMetrics[0]) delete next.metric;
        if (next.band !== false) delete next.band;
        const chosenElement = (this._elements || []).find((item) => item.key === next.element);
        const allValues = (chosenElement?.values || []).map((item) => item.key);
        // Die Vorgabe ("default" in der Liste der App) steht nicht in der YAML.
        const defaultValues = (chosenElement?.values || []).filter((item) => item.default).map((item) => item.key);
        const everything = defaultValues.length > 0 && Array.isArray(next.values) && next.values.length === defaultValues.length && defaultValues.every((key) => next.values.includes(key));
        if (!Array.isArray(next.values) || !next.values.length || everything) delete next.values;
        if ((!allValues.length && chosenElement?.key !== 'energie.speicher') || next.sparkline !== false) delete next.sparkline;
        if (!chosenElement?.sides?.length || next.side === chosenElement.sides[0]) delete next.side;
        if (!chosenElement?.ranges?.length) { delete next.period; delete next.offset; delete next.follow_energy_date; }
        else {
          if (next.period === (chosenElement.ranges.includes('month') ? 'month' : chosenElement.ranges[0])) delete next.period;
          if (!Number(next.offset)) delete next.offset; else next.offset = Math.max(-60, Math.min(0, Math.round(Number(next.offset))));
          if (!next.follow_energy_date) delete next.follow_energy_date;
        }
      }
    }
    this._config = {...next, type: 'custom:zeitarchiv-card'};
    this.dispatchEvent(new CustomEvent('config-changed', {detail: {config: this._config}, bubbles: true, composed: true}));
    this._render();
  }

  // Felder eines Dashboard-Bausteins heißen im Schema kurz (columns, vorjahr, …); ihre Texte tragen das Vorwort element_.
  _fieldLabel(schema) {
    const name = schema.name;
    if (!name) return undefined;
    if (name === 'title' && (this._source === 'element' || this._source === 'table')) return text(this._hass, `title_${this._source}`);
    if (this._source === 'element') {
      if (name === 'follow_energy_date') return text(this._hass, 'element_follow');
      if (ELEMENT_FIELDS.has(name)) return text(this._hass, `element_${name}`);
    }
    return text(this._hass, name);
  }

  // Kurzer Hinweis unter einem Feld; nur dort, wo die Bezeichnung allein nicht sagt, was passiert.
  _fieldHelp(schema) {
    if (schema.name === 'element' && this._config?.element) {
      const key = `desc_${this._config.element}`;
      const described = text(this._hass, key);
      return described === key ? undefined : described;
    }
    const common = {refresh: 'help_refresh', height: 'help_height'}[schema.name];
    if (common) return text(this._hass, common);
    if (this._source !== 'element') return undefined;
    const key = {vorjahr: 'help_vorjahr', diff: 'help_diff', offset: 'help_offset', follow_energy_date: 'help_follow'}[schema.name];
    return key ? text(this._hass, key) : undefined;
  }

  _render() {
    if (!this._hass) return;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.computeLabel = (schema) => this._fieldLabel(schema);
      this._form.computeHelper = (schema) => this._fieldHelp(schema);
      this._form.addEventListener('value-changed', (event) => this._changed(event.detail.value));
      this._hint = document.createElement('div');
      this._hint.style.cssText = 'color: var(--secondary-text-color); font-size: 13px; padding: 4px 0 8px;';
      this.replaceChildren(this._form, this._hint);
    }
    if (this._source === 'entities' && !this._entities) this._loadEntities();
    if (this._source === 'element' && !this._elements) this._loadElements();
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = this._data();
    this._form.error = this._error ? {base: this._error} : undefined;
    const hint = this._hintKey();
    this._hint.textContent = hint ? text(this._hass, hint) : '';
    this._hint.hidden = !hint;
  }

  // Der Administrator baut das Dashboard und sieht alles; was andere Benutzer sehen, zeigt dieser Hinweis.
  _hintKey() {
    const config = this._config || {};
    if (this._source === 'entities') return config.entities?.length ? 'entitiesAdminOnly' : null;
    if (this._source === 'element') return config.element ? 'elementAdminOnly' : null;
    const [list, id] = this._source === 'table' ? [this._tables, config.table_id] : [this._items, config.chart_id];
    const item = id != null ? (list || []).find((entry) => String(entry.id) === String(id)) : null;
    return item && item.shared === false ? 'notShared' : null;
  }
}

// Home Assistant 2026.10 lädt Module aus add_extra_js_url parallel zur App. Läuft ein kleines Modul vor
// dem Polyfill für getrennte Registries, trägt es seine Elemente in die native Registry ein; danach findet
// customElements.get() sie nicht mehr, und die Karte endet mit "Custom element not found"
// (home-assistant/frontend#53890, behoben ab 2026.11). Darum nach dem Start der App prüfen und
// fehlende Elemente noch einmal eintragen; ab 2026.11 findet das nichts mehr zu tun.
const defineElement = (tag, Base) => {
  if (customElements.get(tag)) return;
  try {
    customElements.define(tag, Base);
  } catch {
    // Dieselbe Klasse darf in derselben Registry nur einmal definiert werden: Unterklasse.
    customElements.define(tag, class extends Base {});
  }
};
const whenAppReady = (register, tries = 0) => {
  if (customElements.get('home-assistant')) register();
  else if (tries < 600) setTimeout(() => whenAppReady(register, tries + 1), 100);
};

const registerCard = () => {
  defineElement('zeitarchiv-card', ZeitarchivCard);
  defineElement('zeitarchiv-card-editor', ZeitarchivCardEditor);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === 'zeitarchiv-card')) {
    window.customCards.push({
      type: 'zeitarchiv-card',
      name: 'Zeitarchiv',
      description: TEXTS.en.description,
      preview: true,
    });
  }
};
registerCard();
whenAppReady(registerCard);
