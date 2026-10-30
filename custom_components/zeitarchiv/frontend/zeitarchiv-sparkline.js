// Zeitarchiv-Verlauf: eine kleine Verlaufslinie unter einer Kachelkarte von Home Assistant.
//
// Eine "Karten-Funktion" (card feature): In der Kachelkarte über „Funktion hinzufügen“ wählbar.
// Sie nimmt die Entität der Kachel (context.entity_id), holt über Home Assistant (WebSocket
// zeitarchiv/card/spark, nur für Administratoren) eine kurze Reihe aus dem Zeitarchiv und
// zeichnet sie als SVG, ohne ECharts. Die Entität muss im Zeitarchiv archiviert sein.

const TEXTS = {
  de: {
    name: 'Zeitarchiv-Verlauf',
    range_24h: '24 Std', range_7d: '7 Tage', range_30d: '30 Tage',
    notArchived: 'Nicht archiviert', noData: 'Keine Daten', unsupported: 'Nicht darstellbar',
    unreachable: 'Zeitarchiv nicht erreichbar', stale: 'Stand vor {min} Min', unauthorized: 'Nur für Administratoren',
    app_outdated: 'App zu alt', unknown: 'Fehler',
    range: 'Zeitraum', style: 'Darstellung', color: 'Farbe', min_max: 'Min und Max markieren',
    show_change: 'Änderung anzeigen', include_zero: 'Nullpunkt einbeziehen',
    style_line: 'Linie', style_area: 'Fläche', style_bars: 'Balken',
    color_accent: 'Akzentfarbe', color_trend: 'Nach Trend (steigt oder fällt)',
  },
  en: {
    name: 'Zeitarchiv history',
    range_24h: '24 h', range_7d: '7 days', range_30d: '30 days',
    notArchived: 'Not archived', noData: 'No data', unsupported: 'Not supported',
    unreachable: 'Zeitarchiv not reachable', stale: 'As of {min} min ago', unauthorized: 'Administrators only',
    app_outdated: 'App too old', unknown: 'Error',
    range: 'Period', style: 'Display', color: 'Color', min_max: 'Mark min and max',
    show_change: 'Show change', include_zero: 'Include zero',
    style_line: 'Line', style_area: 'Area', style_bars: 'Bars',
    color_accent: 'Accent color', color_trend: 'By trend (rising or falling)',
  },
};

const RANGES = ['24h', '7d', '30d'];
const REFRESH_SECONDS = 120;
const NUMERIC_DOMAINS = /^(sensor|input_number|number|counter)\./;

// Alles, was aus der App stammt (Einheit), wird maskiert, bevor es in das HTML kommt.
const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const language = (hass) => hass?.locale?.language || hass?.language || document.documentElement.lang || 'en';
const text = (hass, key, values) => {
  const table = language(hass).startsWith('de') ? TEXTS.de : TEXTS.en;
  let result = table[key] ?? TEXTS.en[key] ?? key;
  if (values) result = result.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
  return result;
};

// Abstand bis zum nächsten Abruf: im Normalfall REFRESH_SECONDS, nach Fehlern 10, 20, 40 … Sekunden.
const retryDelaySeconds = (failures) => (failures > 0 ? Math.min(REFRESH_SECONDS, 10 * 2 ** (failures - 1)) : REFRESH_SECONDS);

// Die Verlaufslinie als SVG-Text. values: Zahlen, o: {style, color ('trend'|'accent'), minMax, zero}.
// Alle Koordinaten kommen aus einer Skala; die Farbe als CSS-Variable von Home Assistant.
const sparkSvg = (values, o) => {
  const W = 200;
  const H = 28;
  const pad = 3;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (o.zero) { min = Math.min(0, min); max = Math.max(0, max); }
  if (max === min) { max += 1; min -= 1; }
  const count = values.length;
  const x = (i) => (count === 1 ? W / 2 : pad + ((W - 2 * pad) * i) / (count - 1));
  const y = (v) => H - pad - ((H - 2 * pad) * (v - min)) / (max - min);
  const rising = values[count - 1] >= values[0];
  const color = o.color === 'trend'
    ? (rising ? 'var(--success-color, #43a047)' : 'var(--error-color, #db4437)')
    : 'var(--primary-color, #03a9f4)';
  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-hidden="true">`;
  if (o.style === 'bars') {
    const width = Math.max(1.5, ((W - 2 * pad) / count) * 0.62);
    const base = y(Math.max(min, 0));
    values.forEach((v, i) => {
      const top = y(v);
      svg += `<rect x="${(x(i) - width / 2).toFixed(1)}" y="${Math.min(top, base).toFixed(1)}" width="${width.toFixed(1)}" height="${Math.max(1, Math.abs(base - top)).toFixed(1)}" rx="1" fill="${color}" opacity=".85"/>`;
    });
  } else {
    if (o.style === 'area') svg += `<polygon points="${x(0).toFixed(1)},${H - pad} ${points.join(' ')} ${x(count - 1).toFixed(1)},${H - pad}" fill="${color}" opacity=".16"/>`;
    svg += `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>`;
  }
  if (o.minMax && count > 2) {
    for (const i of [values.indexOf(Math.min(...values)), values.indexOf(Math.max(...values))]) {
      svg += `<circle cx="${x(i).toFixed(1)}" cy="${y(values[i]).toFixed(1)}" r="2.6" fill="var(--card-background-color, #fff)" stroke="${color}" stroke-width="1.6" vector-effect="non-scaling-stroke"/>`;
    }
  }
  svg += `<circle cx="${x(count - 1).toFixed(1)}" cy="${y(values[count - 1]).toFixed(1)}" r="3" fill="${color}"/>`;
  return `${svg}</svg>`;
};

const STYLE = `
  :host { display: block; }
  .box { height: var(--feature-height, 42px); display: flex; flex-direction: column; justify-content: center; gap: 2px; padding: 0 2px; box-sizing: border-box; }
  svg { display: block; width: 100%; flex: 1 1 auto; min-height: 0; overflow: visible; }
  .foot { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; line-height: 12px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .note { font-size: 12px; color: var(--secondary-text-color); text-align: center; }
  .note.error { color: var(--error-color); }
  .warn { color: var(--warning-color, #b26a00); }
  .up { color: var(--success-color, #43a047); }
  .down { color: var(--error-color, #db4437); }
`;

class ZeitarchivSparkline extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><div class="box"></div>`;
    this._box = this.shadowRoot.querySelector('.box');
    this._config = null;
    this._hass = null;
    this._context = null;
    this._timer = null;
    this._visible = true;
    this._loading = false;
    this._failures = 0;
    this._lastGood = 0;
    this._data = null;
    // Ein Klick im Streifen soll nicht die Detailansicht der Kachel öffnen.
    this.addEventListener('click', (event) => event.stopPropagation());
  }

  static getStubConfig() {
    return {type: 'custom:zeitarchiv-sparkline', range: '24h', style: 'line', color: 'accent', show_change: true};
  }

  // Einstellungen im Editor der Kachelkarte.
  static getConfigForm() {
    const select = (name, options) => ({name, selector: {select: {mode: 'dropdown', options}}});
    const lang = {locale: {language: document.documentElement.lang || 'en'}};
    const label = (key) => text(lang, key);
    return {
      schema: [
        select('range', RANGES.map((value) => ({value, label: label(`range_${value}`)}))),
        select('style', ['line', 'area', 'bars'].map((value) => ({value, label: label(`style_${value}`)}))),
        select('color', ['accent', 'trend'].map((value) => ({value, label: label(`color_${value}`)}))),
        {name: 'min_max', selector: {boolean: {}}},
        {name: 'show_change', selector: {boolean: {}}},
        {name: 'include_zero', selector: {boolean: {}}},
      ],
      computeLabel: (schema) => label(schema.name),
    };
  }

  setConfig(config) {
    this._config = {range: '24h', style: 'line', color: 'accent', ...config};
    if (!RANGES.includes(this._config.range)) this._config.range = '24h';
    this._failures = 0;
    this._data = null;
    this._load();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }

  set context(context) {
    const changed = this._context?.entity_id !== context?.entity_id;
    this._context = context;
    if (changed) { this._data = null; this._load(); }
  }

  connectedCallback() {
    if (typeof IntersectionObserver !== 'undefined') {
      this._observer = new IntersectionObserver((entries) => {
        this._visible = entries.some((entry) => entry.isIntersecting);
        if (this._visible && Date.now() - this._lastGood > REFRESH_SECONDS * 1000) this._load();
      });
      this._observer.observe(this);
    }
    this._load();
  }

  disconnectedCallback() {
    clearTimeout(this._timer);
    this._timer = null;
    this._observer?.disconnect();
  }

  _schedule() {
    clearTimeout(this._timer);
    if (!this.isConnected) return;
    this._timer = setTimeout(() => {
      if (!document.hidden && this._visible) this._load();
      else this._schedule();
    }, retryDelaySeconds(this._failures) * 1000);
  }

  _note(key, error = false) {
    this._box.innerHTML = `<div class="note${error ? ' error' : ''}">${text(this._hass, key)}</div>`;
  }

  async _load() {
    const entityId = this._context?.entity_id;
    if (this._loading || !this._config || !this._hass || !entityId) return;
    this._loading = true;
    try {
      const result = await this._hass.callWS({type: 'zeitarchiv/card/spark', entity_id: entityId, range: this._config.range});
      this._data = result;
      this._lastGood = Date.now();
      this._failures = 0;
      this._render(false);
    } catch (err) {
      this._failures += 1;
      const code = err && err.code;
      if (code === 'not_found') this._note('notArchived');
      else if (this._data && ['unreachable', 'busy', 'auth_failed'].includes(code)) this._render(true);
      else this._note(code === 'unauthorized' || code === 'app_outdated' ? code : (code === 'unreachable' ? 'unreachable' : 'unknown'), true);
    } finally {
      this._loading = false;
      this._schedule();
    }
  }

  _render(stale) {
    const data = this._data;
    if (!data || !data.supported) { this._note('unsupported'); return; }
    const values = (data.points || []).map((point) => point[1]).filter(Number.isFinite);
    if (values.length < 2) { this._note('noData'); return; }
    const c = this._config;
    const change = values[values.length - 1] - values[0];
    const digits = Number.isInteger(data.decimals) ? data.decimals : (Math.abs(change) < 10 ? 1 : 0);
    const number = new Intl.NumberFormat(language(this._hass), {minimumFractionDigits: digits, maximumFractionDigits: digits});
    const unit = data.unit ? ` ${esc(data.unit)}` : '';
    const left = stale
      ? `<span class="warn">${text(this._hass, 'stale', {min: Math.max(1, Math.round((Date.now() - this._lastGood) / 60000))})}</span>`
      : `<span>${text(this._hass, `range_${c.range}`)}</span>`;
    const right = c.show_change
      ? `<span class="${change >= 0 ? 'up' : 'down'}">${change >= 0 ? '+' : '−'}${number.format(Math.abs(change))}${unit}</span>`
      : '<span></span>';
    this._box.innerHTML = `${sparkSvg(values, {style: c.style, color: c.color, minMax: Boolean(c.min_max), zero: Boolean(c.include_zero)})}<div class="foot">${left}${right}</div>`;
  }
}

if (!customElements.get('zeitarchiv-sparkline')) {
  customElements.define('zeitarchiv-sparkline', ZeitarchivSparkline);
  window.customCardFeatures = window.customCardFeatures || [];
  window.customCardFeatures.push({
    type: 'zeitarchiv-sparkline',
    name: TEXTS[(document.documentElement.lang || 'en').startsWith('de') ? 'de' : 'en'].name,
    configurable: true,
    // Nur Zahlen-Entitäten; ob das Zeitarchiv sie archiviert, zeigt das Feature selbst an.
    isSupported: (hass, context) => NUMERIC_DOMAINS.test(context?.entity_id || ''),
  });
}
