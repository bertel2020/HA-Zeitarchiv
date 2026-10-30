// Ein gemeinsamer HTML-Maskierer für alle Skripte, die HTML als String
// zusammensetzen (innerHTML, Template-Literale). Vorher hatte jede Datei ihren
// eigenen, und sie unterschieden sich: einer ließ die Anführungszeichen aus
// (in Attributen ein Ausbruch), einer das & (in Text ein kaputtes Zeichen).
// Maskiert & < > " ' — damit taugt das Ergebnis für Text UND für
// Attributwerte in " oder '. null/undefined ergeben einen leeren Text.
// Wird in base.html für jede Seite geladen, wie i18n.js.
(function () {
  const HTML_ESCAPES = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
  window.escapeHtml = function (value) {
    return (value == null ? '' : String(value)).replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);
  };
})();
