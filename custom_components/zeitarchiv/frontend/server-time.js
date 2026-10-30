// Kalenderangaben in der Zeitzone des SERVERS statt der des Browsers.
//
// Der Server rechnet jeden Zeitraum in seiner Zeitzone (Einstellung des Add-ons)
// und liefert Zeitstempel. Wer daraus im Browser mit getFullYear()/getMonth()
// oder toLocaleDateString() ohne timeZone ein Datum macht, bekommt das Datum der
// BROWSER-Zeitzone: liegt sie hinter dem Server (z. B. Portugal bei Server in
// Deutschland), wird aus dem 01.10. 00:00 der 30.09. 23:00, und die Oberfläche
// zeigt "September" bzw. das Vorjahr. Die Zone steht als data-tz am <html>.
window.ServerTime = (() => {
  const zoneName = (() => {
    const name = document.documentElement.dataset.tz || '';
    if (!name) return undefined;
    try {
      new Intl.DateTimeFormat('en-US', {timeZone: name});
      return name;
    } catch (e) {
      return undefined;  // unbekannte Zone: wie bisher die des Browsers
    }
  })();

  // Optionen für toLocale*String() um die Serverzone ergänzen.
  function withZone(options) {
    return zoneName ? {...options, timeZone: zoneName} : options;
  }

  const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const partsFormat = new Intl.DateTimeFormat('en-US', withZone({
    year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', weekday: 'short', hourCycle: 'h23',
  }));

  // Kalenderbestandteile eines Zeitstempels in der Serverzone:
  // month 1–12, weekday 0 = Sonntag (wie Date.getDay()).
  function parts(epochSeconds) {
    const p = {};
    for (const {type, value} of partsFormat.formatToParts(new Date(epochSeconds * 1000))) p[type] = value;
    return {
      year: parseInt(p.year, 10), month: parseInt(p.month, 10), day: parseInt(p.day, 10),
      hour: parseInt(p.hour, 10), minute: parseInt(p.minute, 10), weekday: WEEKDAYS.indexOf(p.weekday),
    };
  }

  const wallFormat = new Intl.DateTimeFormat('en-US', withZone({
    year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', second: 'numeric', hourCycle: 'h23',
  }));

  // Umkehrung von parts(): Die Uhrzeit "year-month-day hour:minute:second" in der
  // Serverzone als Zeitstempel (Sekunden). Ein Eingabefeld (datetime-local,
  // month) liefert nur Uhrzeit-Ziffern ohne Zone; new Date(…) läse sie in der
  // BROWSER-Zone und verschöbe den Wert um den Unterschied zum Server. month
  // 1–12; Überläufe (day 0 = letzter Tag des Vormonats) rechnet Date.UTC. Zwei
  // Durchgänge, damit der Versatz an einer Sommerzeitgrenze stimmt.
  function toEpoch(year, month, day, hour = 0, minute = 0, second = 0) {
    const wall = Date.UTC(year, month - 1, day, hour, minute, second) / 1000;
    let ts = wall;
    for (let i = 0; i < 2; i++) {
      const p = {};
      for (const {type, value} of wallFormat.formatToParts(new Date(ts * 1000))) p[type] = value;
      const shown = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) / 1000;
      ts += wall - shown;
    }
    return ts;
  }

  return {zone: zoneName, withZone, parts, toEpoch};
})();
