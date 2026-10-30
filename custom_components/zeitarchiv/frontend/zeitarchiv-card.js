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
    chooseChart: 'Bitte ein Chart, eine Tabelle oder Entitäten aus dem Zeitarchiv wählen.',
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
    chart_id: 'Chart aus dem Zeitarchiv',
    entities: 'Entitäten (nur archivierte)',
    period: 'Zeitraum',
    style: 'Darstellung',
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
    refresh: 'Aktualisierung (Sekunden)',
    height: 'Höhe (Pixel)',
    tap_action: 'Beim Tippen',
    notSupportedShort: 'noch nicht darstellbar',
    description: 'Zeigt ein gespeichertes Chart oder Entitäten aus dem Zeitarchiv.',
  },
  en: {
    loading: 'Loading …',
    chartLabel: 'Chart {title}', sum: 'total', last: 'latest', more: 'and {n} more',
    noData: 'No data',
    chooseChart: 'Please choose a chart, a table or entities from Zeitarchiv.',
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
    chart_id: 'Chart from Zeitarchiv',
    entities: 'Entities (archived only)',
    period: 'Period',
    style: 'Display',
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
    refresh: 'Refresh (seconds)',
    height: 'Height (pixels)',
    tap_action: 'On tap',
    notSupportedShort: 'not supported yet',
    description: 'Shows a saved chart or entities from Zeitarchiv.',
  },
};

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
    const [echartsSource, render, numberFormat, tooltipHold, serverTime, htmlEscape, stateEntities, tableCompute, tableRender, tableCss, catalog] = await Promise.all([
      fetchText('echarts.min.js'), fetchText('chart-tile-render.js'), fetchText('number-format.js'),
      fetchText('tooltip-hold.js'), fetchText('server-time.js'), fetchText('html-escape.js'),
      fetchText('state-entities.js'), fetchText('table-compute.js'), fetchText('table-tile-render.js'),
      fetchText('table.css'), fetchText('catalog.json'),
    ]);
    const module = {exports: {}};
    new Function('module', 'exports', `${echartsSource}\n//# sourceURL=zeitarchiv/echarts.min.js`).call(module.exports, module, module.exports);
    return {echarts: module.exports, render, numberFormat, tooltipHold, serverTime, htmlEscape, stateEntities, tableCompute, tableRender, tableCss, catalog: JSON.parse(catalog)};
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
  return {render, setVars: (map) => Object.assign(vars, map), tables: {TableCompute: win.TableCompute, TableTileRender}};
};

const runtimeFor = async (settings) => {
  const sources = await loadSources();
  const key = `${settings.timezone}|${settings.language}|${settings.dark}`;
  if (!runtimes.has(key)) runtimes.set(key, buildRuntime(sources, settings));
  return {...runtimes.get(key), echarts: sources.echarts, tableCss: sources.tableCss};
};

// --- Karte -----------------------------------------------------------------------------

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
  .tablebox { overflow: auto; padding: 4px 8px 12px; color: var(--primary-text-color); }
  .tablebox table { margin: 0; }
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
  }
`;

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
    this._lastGood = 0;
    this._failures = 0;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card>
        <div class="header" part="header" hidden></div>
        <div class="body">
          <div class="chart" role="img" hidden></div>
          <div class="tablebox" hidden></div>
          <style class="tablecss"></style>
          <div class="note" role="status"></div>
        </div>
        <div class="badge" role="status" hidden></div>
      </ha-card>`;
    this._els = {
      header: this.shadowRoot.querySelector('.header'), chart: this.shadowRoot.querySelector('.chart'),
      note: this.shadowRoot.querySelector('.note'), badge: this.shadowRoot.querySelector('.badge'),
      table: this.shadowRoot.querySelector('.tablebox'),
      tableCss: this.shadowRoot.querySelector('.tablecss'),
    };
    this._els.card = this.shadowRoot.querySelector('ha-card');
    this._wireTableTips();
    this._wireAction();
  }

  // Tippen: die Standard-Aktion von Home Assistant (tap_action). Die Karte löst nur das Ereignis aus,
  // das Öffnen eines Dashboards, einer URL oder einer Aktion erledigt HA. Ohne Aktion ändert sich nichts.
  _wireAction() {
    const card = this._els.card;
    card.addEventListener('click', () => this._fireAction());
    card.addEventListener('keydown', (event) => {
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
    this._lastGood = 0;
    this._failures = 0;
    this._generation += 1;
    this._applyAction();
    if (this._hass) this._load();
    else this._showNote(this._hasSource() ? 'loading' : 'chooseChart');
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this._config) { this._look = this._lookOf(hass); this._load(); return; }
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
      this._resize = new ResizeObserver(() => this._chart && this._chart.resize());
      this._resize.observe(this._els.chart);
    }
    if (this._hass && this._config) this._load();
  }

  disconnectedCallback() {
    clearTimeout(this._timer);
    this._timer = null;
    this._observer?.disconnect();
    window.removeEventListener('scroll', this._hideTableTip, true);
    this._hideTableTip();
    this._resize?.disconnect();
    if (this._chart) { this._chart.dispose(); this._chart = null; }
  }

  _hasSource() {
    return Boolean(this._config?.entities?.length || this._config?.chart_id || this._config?.table_id);
  }

  // Die Anfrage an Home Assistant: Entitäten direkt oder ein gespeichertes Chart.
  _request() {
    const config = this._config;
    // Breite der Karte: der Zeitstrahl in Jahr und Dekade wird in dieser Breite vom Server zusammengefasst.
    const px = Math.min(4000, Math.max(0, Math.round(this.getBoundingClientRect().width)));
    if (config.entities.length) {
      return {type: 'zeitarchiv/card/series', entity_ids: config.entities, period: config.period || 'month', style: config.style || 'auto', px};
    }
    if (config.table_id && !config.chart_id) return {type: 'zeitarchiv/card/table', table_id: config.table_id};
    return {type: 'zeitarchiv/card/chart', chart_id: config.chart_id, px};
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
    const key = err && typeof err === 'object' && err.code && TEXTS.en[err.code] ? err.code : (err && err.script ? 'script' : 'unknown');
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
    if (result.table) { await this._drawTable(result); return; }
    this._els.table.hidden = true;
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
      spec, data: result.data, series, viewType: R.viewTypeFor(spec, series), multiYear, hiddenSet: undefined, style,
    });
    this._els.chart.setAttribute('aria-label', this._describe(this._config.title || result.name, series, result.spec));
    this._applyAction();
    this._chart.resize();
    this._shown = true;
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
    if (table.empty) { this._showNote('noVisible'); return; }
    if (this._els.tableCss.textContent !== runtime.tableCss) this._els.tableCss.textContent = runtime.tableCss;
    this._els.note.hidden = true;
    this._els.chart.hidden = true;
    this._els.chart.removeAttribute('aria-label');
    this._els.table.hidden = false;
    this._els.table.style.maxHeight = this._explicitHeight ? `${Math.max(120, Number(this._config.height) || 260)}px` : '';
    this._els.table.innerHTML = TableTileRender.buildHtml({...table, style: result.table.style || {}});
    TableTileRender.afterInsert(this._els.table);
    this._applyAction();
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
    this._entities = null;
    this._source = 'chart';
    this._error = null;
    this._form = null;
  }

  setConfig(config) {
    this._config = config || {};
    const pickedEntities = Array.isArray(this._config.entities) && this._config.entities.length;
    if (pickedEntities) this._source = 'entities';
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
      {value: 'entities', label: label('sourceEntities')},
    ])];
    if (this._source === 'entities') {
      schema.push(
        {name: 'entities', required: true, selector: {entity: {multiple: true, include_entities: (this._entities || []).map((e) => e.entity_id)}}},
        select('period', ['month', 'day', 'week', 'year', '24h', '7d', '30d'].map((value) => ({value, label: label(`period_${value}`)}))),
        select('style', ['auto', 'stacked', 'percent'].map((value) => ({value, label: label(`style_${value}`)}))),
      );
    } else if (this._source === 'table') {
      schema.push({...select('table_id', tableOptions), required: true});
    } else {
      schema.push({...select('chart_id', chartOptions), required: true});
    }
    schema.push(
      {name: 'title', selector: {text: {}}},
      {name: 'refresh', selector: {number: {min: 15, max: 3600, step: 15, mode: 'box', unit_of_measurement: 's'}}},
      {name: 'height', selector: {number: {min: 120, max: 800, step: 10, mode: 'box', unit_of_measurement: 'px'}}},
      {name: 'tap_action', selector: {ui_action: {default_action: 'none'}}},
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
    }
    return data;
  }

  _changed(value) {
    const next = {...value};
    const source = next.source || this._source;
    delete next.source;
    if (source !== this._source) {
      this._source = source;
      delete next.chart_id; delete next.table_id; delete next.entities; delete next.period; delete next.style;
      if (source === 'entities') this._loadEntities();
    }
    for (const key of ['chart_id', 'table_id']) {
      if (next[key] !== undefined && next[key] !== '') next[key] = Number(next[key]);
      else delete next[key];
    }
    if (!next.title) delete next.title;
    if (!next.tap_action || !next.tap_action.action || next.tap_action.action === 'none') delete next.tap_action;
    if (this._source !== 'entities') for (const key of ['entities', 'period', 'style']) delete next[key];
    if (this._source !== 'chart') delete next.chart_id;
    if (this._source !== 'table') delete next.table_id;
    this._config = {...next, type: 'custom:zeitarchiv-card'};
    this.dispatchEvent(new CustomEvent('config-changed', {detail: {config: this._config}, bubbles: true, composed: true}));
    this._render();
  }

  _render() {
    if (!this._hass) return;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.computeLabel = (schema) => text(this._hass, schema.name);
      this._form.addEventListener('value-changed', (event) => this._changed(event.detail.value));
      this._hint = document.createElement('div');
      this._hint.style.cssText = 'color: var(--secondary-text-color); font-size: 13px; padding: 4px 0 8px;';
      this.replaceChildren(this._form, this._hint);
    }
    if (this._source === 'entities' && !this._entities) this._loadEntities();
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
    const [list, id] = this._source === 'table' ? [this._tables, config.table_id] : [this._items, config.chart_id];
    const item = id != null ? (list || []).find((entry) => String(entry.id) === String(id)) : null;
    return item && item.shared === false ? 'notShared' : null;
  }
}

if (!customElements.get('zeitarchiv-card')) {
  customElements.define('zeitarchiv-card', ZeitarchivCard);
  customElements.define('zeitarchiv-card-editor', ZeitarchivCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'zeitarchiv-card',
    name: 'Zeitarchiv',
    description: TEXTS.en.description,
    preview: true,
  });
}
