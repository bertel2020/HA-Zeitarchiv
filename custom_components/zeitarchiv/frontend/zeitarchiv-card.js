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
    noData: 'Keine Daten',
    chooseChart: 'Bitte ein Chart aus dem Zeitarchiv wählen.',
    unsupported: 'Diese Darstellung zeigt die Karte noch nicht.',
    openLink: 'Im Zeitarchiv öffnen',
    stale: 'Stand vor {min} Min, Zeitarchiv nicht erreichbar',
    not_loaded: 'Keine Zeitarchiv-Verbindung eingerichtet.',
    app_outdated: 'Die Zeitarchiv-App ist zu alt für die Karte. Bitte die App aktualisieren.',
    not_found: 'Dieses Chart gibt es im Zeitarchiv nicht mehr.',
    busy: 'Zeitarchiv ist gerade beschäftigt, nächster Versuch folgt.',
    auth_failed: 'Zeitarchiv hat die Zugangsdaten abgelehnt.',
    unreachable: 'Zeitarchiv ist nicht erreichbar.',
    unauthorized: 'Die Karte ist nur für Administratoren sichtbar.',
    unknown: 'Die Karte konnte nicht geladen werden.',
    spec: 'Die Karte passt nicht zur Version der Zeitarchiv-App.',
    script: 'Die Karte konnte ihre Dateien nicht laden.',
    chart_id: 'Chart aus dem Zeitarchiv',
    title: 'Titel (leer: Name des Charts)',
    refresh: 'Aktualisierung (Sekunden)',
    height: 'Höhe (Pixel)',
    link: 'Link zum Zeitarchiv (z. B. /hassio/ingress/…)',
    notSupportedShort: 'noch nicht darstellbar',
    description: 'Zeigt ein gespeichertes Chart aus dem Zeitarchiv.',
  },
  en: {
    loading: 'Loading …',
    noData: 'No data',
    chooseChart: 'Please choose a chart from Zeitarchiv.',
    unsupported: 'The card cannot show this kind of chart yet.',
    openLink: 'Open in Zeitarchiv',
    stale: 'As of {min} min ago, Zeitarchiv not reachable',
    not_loaded: 'No Zeitarchiv connection is set up.',
    app_outdated: 'The Zeitarchiv app is too old for the card. Please update the app.',
    not_found: 'This chart no longer exists in Zeitarchiv.',
    busy: 'Zeitarchiv is busy, trying again shortly.',
    auth_failed: 'Zeitarchiv rejected the credentials.',
    unreachable: 'Zeitarchiv is not reachable.',
    unauthorized: 'The card is only visible to administrators.',
    unknown: 'The card could not be loaded.',
    spec: 'The card does not match the version of the Zeitarchiv app.',
    script: 'The card could not load its files.',
    chart_id: 'Chart from Zeitarchiv',
    title: 'Title (empty: chart name)',
    refresh: 'Refresh (seconds)',
    height: 'Height (pixels)',
    link: 'Link to Zeitarchiv (e.g. /hassio/ingress/…)',
    notSupportedShort: 'not supported yet',
    description: 'Shows a saved chart from Zeitarchiv.',
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
    const [echartsSource, render, numberFormat, tooltipHold, serverTime] = await Promise.all([
      fetchText('echarts.min.js'), fetchText('chart-tile-render.js'), fetchText('number-format.js'),
      fetchText('tooltip-hold.js'), fetchText('server-time.js'),
    ]);
    const module = {exports: {}};
    new Function('module', 'exports', echartsSource).call(module.exports, module, module.exports);
    return {echarts: module.exports, render, numberFormat, tooltipHold, serverTime};
  })().catch((err) => { sourcesPromise = null; throw err; });
  return sourcesPromise;
};

const evaluate = (source, names, values) => new Function(...names, source)(...values);

const buildRuntime = (sources, {timezone, language, dark}) => {
  const palette = dark ? PALETTES.dark : PALETTES.light;
  const win = {ZA_FORMAT: language};
  const doc = {documentElement: {dataset: {tz: timezone, format: language}}, body: {}};
  const getComputedStyle = () => ({
    getPropertyValue: (name) => {
      const match = /^--chart-(\d)$/.exec(name);
      if (match) return palette[Number(match[1]) - 1] || '';
      return name === '--font-scale' ? '1' : '';
    },
  });
  const t = (value, values) => (values ? value.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m)) : value);
  evaluate(sources.numberFormat, ['window', 'document'], [win, doc]);
  evaluate(sources.tooltipHold, ['window', 'document'], [win, doc]);
  evaluate(sources.serverTime, ['window', 'document'], [win, doc]);
  // Nur Zahlen-Charts: die Zustandsansichten der App (state-entities.js) gehören
  // nicht zur Karte, ihre Zeitraum-Listen schon, weil draw() sie abfragt.
  const StateEntities = {
    SERVER_SHARE_RANGES: ['month', 'year', 'decade'],
    COLUMN_RANGES: ['year', 'decade'],
    defaultMode: (range) => (['month', 'year', 'decade'].includes(range) ? 'shares' : 'timeline'),
  };
  return evaluate(
    `${sources.render}\nreturn window.ChartTileRender;`,
    ['window', 'document', 'getComputedStyle', 't', 'NumberFormat', 'TooltipHold', 'StateEntities', 'PeriodNavigation', 'echarts'],
    [win, doc, getComputedStyle, t, win.NumberFormat, win.TooltipHold, StateEntities, {}, sources.echarts],
  );
};

const runtimeFor = async (settings) => {
  const sources = await loadSources();
  const key = `${settings.timezone}|${settings.language}|${settings.dark}`;
  if (!runtimes.has(key)) runtimes.set(key, buildRuntime(sources, settings));
  return {render: runtimes.get(key), echarts: sources.echarts};
};

// --- Karte -----------------------------------------------------------------------------

const STYLE = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .header { padding: 12px 16px 0; font-size: var(--ha-card-header-font-size, 18px); font-weight: 500; color: var(--primary-text-color); }
  .body { position: relative; padding: 8px 8px 12px; }
  .chart { width: 100%; }
  .note { padding: 16px; color: var(--secondary-text-color); }
  .note.error { color: var(--error-color); }
  .badge { display: inline-block; margin: 0 16px 8px; padding: 2px 10px; border-radius: 999px; font-size: 12px;
           color: var(--warning-color, #b26a00); border: 1px solid currentColor; }
  .footer { padding: 0 16px 12px; font-size: 13px; }
  .footer a { color: var(--primary-color); text-decoration: none; }
  .footer a:hover { text-decoration: underline; }
  [hidden] { display: none !important; }
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
    this._lastGood = 0;
    this._failures = 0;
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card>
        <div class="header" part="header" hidden></div>
        <div class="body">
          <div class="chart" hidden></div>
          <div class="note"></div>
        </div>
        <div class="badge" hidden></div>
        <div class="footer" hidden></div>
      </ha-card>`;
    this._els = {
      header: this.shadowRoot.querySelector('.header'), chart: this.shadowRoot.querySelector('.chart'),
      note: this.shadowRoot.querySelector('.note'), badge: this.shadowRoot.querySelector('.badge'),
      footer: this.shadowRoot.querySelector('.footer'),
    };
  }

  static getConfigElement() { return document.createElement('zeitarchiv-card-editor'); }

  static getStubConfig() { return {}; }

  setConfig(config) {
    this._config = {refresh: 60, height: 260, ...config};
    if (this._config.chart_id != null) this._config.chart_id = Number(this._config.chart_id);
    this._els.chart.style.height = `${Math.max(120, Number(this._config.height) || 260)}px`;
    this._lastGood = 0;
    this._failures = 0;
    if (this._hass) this._load();
    else this._showNote(this._config.chart_id ? 'loading' : 'chooseChart');
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first && this._config) this._load();
  }

  getCardSize() { return Math.ceil((Number(this._config?.height) || 260) / 50) + 1; }

  connectedCallback() {
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
    this._resize?.disconnect();
    if (this._chart) { this._chart.dispose(); this._chart = null; }
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
    note.hidden = false;
    this._els.chart.hidden = true;
  }

  _setHeader(name) {
    const title = this._config.title || name;
    this._els.header.textContent = title || '';
    this._els.header.hidden = !title;
  }

  _setFooter() {
    const link = this._config.link;
    this._els.footer.replaceChildren();
    if (link) {
      const anchor = document.createElement('a');
      anchor.href = link;
      anchor.textContent = text(this._hass, 'openLink');
      this._els.footer.append(anchor);
    }
    this._els.footer.hidden = !link;
  }

  async _load() {
    if (this._loading || !this._config || !this._hass) return;
    if (!this._config.chart_id) { this._showNote('chooseChart'); return; }
    this._loading = true;
    try {
      const result = await this._hass.callWS({type: 'zeitarchiv/card/chart', chart_id: this._config.chart_id});
      await this._draw(result);
      this._lastGood = Date.now();
      this._failures = 0;
      this._els.badge.hidden = true;
    } catch (err) {
      this._failures += 1;
      this._fail(err);
    } finally {
      this._loading = false;
      this._schedule();
    }
  }

  _fail(err) {
    const key = err && typeof err === 'object' && err.code && TEXTS.en[err.code] ? err.code : (err && err.script ? 'script' : 'unknown');
    if (key !== 'unknown' && key !== 'script' && err.code !== 'unauthorized') console.debug('Zeitarchiv-Karte:', err.code, err.message);
    else console.warn('Zeitarchiv-Karte:', err);
    // Ein Ausfall nach einem guten Stand lässt das Bild stehen und sagt nur, wie alt es ist.
    if (this._chart && this._lastGood && ['unreachable', 'busy', 'auth_failed'].includes(key)) {
      this._els.badge.textContent = text(this._hass, 'stale', {min: Math.max(1, Math.round((Date.now() - this._lastGood) / 60000))});
      this._els.badge.hidden = false;
      return;
    }
    this._showNote(key, true);
  }

  async _draw(result) {
    if (!result || result.spec_version !== SPEC_VERSION) { const err = new Error('spec_version'); err.code = 'spec'; throw err; }
    this._setHeader(result.name);
    this._setFooter();
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
    R.draw(this._chart, {
      spec, data: result.data, series, viewType: R.viewTypeFor(spec, series),
      multiYear: null, hiddenSet: undefined, style: this._themeStyle(),
    });
    this._chart.resize();
  }

  // Die Farben, die draw() aus dem CSS der App liest, aus dem Thema von Home Assistant.
  _themeStyle() {
    const css = getComputedStyle(this);
    const get = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    const map = {
      '--border': get('--divider-color', '#e0e0e0'),
      '--ink-faint': get('--secondary-text-color', '#727272'),
      '--ink-muted': get('--primary-text-color', '#212121'),
      '--surface': get('--card-background-color', '#ffffff'),
      '--font-mono': get('--ha-font-family-body', 'Roboto, sans-serif'),
    };
    return {getPropertyValue: (name) => map[name] ?? ''};
  }
}

// --- Editor ----------------------------------------------------------------------------

class ZeitarchivCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
    this._hass = null;
    this._items = null;
    this._form = null;
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    if (first) this._loadItems();
  }

  async _loadItems() {
    try {
      const result = await this._hass.callWS({type: 'zeitarchiv/card/items'});
      this._items = result.items || [];
    } catch (err) {
      this._items = [];
      this._error = err && err.code && TEXTS.en[err.code] ? text(this._hass, err.code) : text(this._hass, 'unknown');
    }
    this._render();
  }

  _schema() {
    const options = (this._items || []).map((item) => ({
      value: String(item.id),
      label: item.supported ? item.name : `${item.name} (${text(this._hass, 'notSupportedShort')})`,
    }));
    return [
      {name: 'chart_id', required: true, selector: {select: {mode: 'dropdown', options}}},
      {name: 'title', selector: {text: {}}},
      {name: 'refresh', selector: {number: {min: 15, max: 3600, step: 15, mode: 'box', unit_of_measurement: 's'}}},
      {name: 'height', selector: {number: {min: 120, max: 800, step: 10, mode: 'box', unit_of_measurement: 'px'}}},
      {name: 'link', selector: {text: {}}},
    ];
  }

  _render() {
    if (!this._hass) return;
    if (!this._form) {
      this._error = null;
      this._form = document.createElement('ha-form');
      this._form.computeLabel = (schema) => text(this._hass, schema.name);
      this._form.addEventListener('value-changed', (event) => {
        const value = {...event.detail.value};
        if (value.chart_id !== undefined && value.chart_id !== '') value.chart_id = Number(value.chart_id);
        for (const key of ['title', 'link']) if (!value[key]) delete value[key];
        this._config = {...value, type: 'custom:zeitarchiv-card'};
        this.dispatchEvent(new CustomEvent('config-changed', {detail: {config: this._config}, bubbles: true, composed: true}));
      });
      this.replaceChildren(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = {...this._config, chart_id: this._config.chart_id != null ? String(this._config.chart_id) : undefined};
    if (this._error) this._form.error = {base: this._error};
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
    preview: false,
  });
}
