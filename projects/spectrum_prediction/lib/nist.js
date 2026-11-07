// NIST Atomic Spectra Database (ASD) line-list parser for the CSV export (format=2).
// PubChem element records point to ASD in their "Atomic Spectra" section; the collector follows
// that pointer, so every atomic line keeps PubChem -> NIST provenance.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  function splitCsvLine(line) {
    const cells = [];
    let cell = '', quoted = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (quoted) {
        if (ch === '"' && line[i + 1] === '"') { cell += '"'; i++; }
        else if (ch === '"') quoted = false;
        else cell += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ',') { cells.push(cell); cell = ''; }
      else cell += ch;
    }
    cells.push(cell);
    // ASD wraps values as ="value" so spreadsheets keep them as text.
    return cells.map(c => c.replace(/^="?/, '').replace(/"$/, '').trim());
  }
  function number(text) {
    if (text === undefined || text === null) return null;
    const cleaned = String(text).replace(/[\[\]()?+*]/g, '').trim();
    if (!cleaned) return null;
    const value = Number(cleaned);
    return Number.isFinite(value) ? value : null;
  }

  // Returns {medium, columns, lines:[{wavelength_nm, observed, aki, gk, gi, ei_cm1, ek_cm1,
  // intensity, accuracy, lower, upper}]}. Throws on an HTML/error page instead of guessing.
  function parseLines(text) {
    const rows = String(text).split(/\r?\n/).filter(r => r.trim());
    if (!rows.length) throw new Error('NIST ASD response is empty');
    if (/<html|<!DOCTYPE/i.test(rows[0])) throw new Error('NIST ASD returned HTML, not CSV: ' + rows.slice(0, 3).join(' ').slice(0, 200));
    const columns = splitCsvLine(rows[0]).filter(Boolean);
    const index = name => columns.findIndex(c => c.indexOf(name) === 0);
    const obs = columns.findIndex(c => /^obs_wl_(air|vac)\(nm\)$/.test(c));
    const ritz = columns.findIndex(c => /^ritz_wl_(air|vac)\(nm\)$/.test(c));
    if (obs < 0 && ritz < 0) throw new Error('NIST ASD CSV lacks wavelength columns: ' + columns.join(','));
    const medium = (columns[obs >= 0 ? obs : ritz].indexOf('_air') > 0) ? 'air' : 'vacuum';
    const col = {aki: index('Aki'), gi: index('g_i'), gk: index('g_k'), ei: index('Ei('), ek: index('Ek('),
      intens: index('intens'), acc: index('Acc'), confI: index('conf_i'), termI: index('term_i'),
      jI: index('J_i'), confK: index('conf_k'), termK: index('term_k'), jK: index('J_k')};
    const lines = [];
    for (let r = 1; r < rows.length; r++) {
      const c = splitCsvLine(rows[r]);
      const observed = obs >= 0 ? number(c[obs]) : null;
      const computed = ritz >= 0 ? number(c[ritz]) : null;
      const wavelength = observed !== null ? observed : computed;
      if (wavelength === null) continue;
      const pick = k => (col[k] >= 0 ? c[col[k]] : '');
      lines.push({wavelength_nm: wavelength, observed: observed !== null, aki: number(pick('aki')),
        gi: number(pick('gi')), gk: number(pick('gk')), ei_cm1: number(pick('ei')), ek_cm1: number(pick('ek')),
        intensity: pick('intens') || null, accuracy: pick('acc') || null,
        lower: [pick('confI'), pick('termI'), pick('jI')].join(' ').trim(),
        upper: [pick('confK'), pick('termK'), pick('jK')].join(' ').trim()});
    }
    return {medium, columns, lines};
  }

  // Query URL for one neutral spectrum on a wavelength window; mirrors ASD's own form fields.
  function linesUrl(symbol, lowNm, highNm, base) {
    const params = ['spectra=' + encodeURIComponent(symbol + ' I'), 'limits_type=0', 'low_w=' + lowNm, 'upp_w=' + highNm,
      'unit=1', 'de=0', 'format=2', 'line_out=0', 'en_unit=0', 'output=0', 'page_size=15', 'show_obs_wl=1',
      'show_calc_wl=1', 'order_out=0', 'show_av=2', 'tsb_value=0', 'A_out=0', 'intens_out=on', 'allowed_out=1',
      'forbid_out=1', 'conf_out=on', 'term_out=on', 'enrg_out=on', 'J_out=on', 'g_out=on', 'submit=Retrieve+Data'];
    return (base || 'https://physics.nist.gov/cgi-bin/ASD/lines1.pl') + '?' + params.join('&');
  }

  S.nist = Object.freeze({splitCsvLine, parseLines, linesUrl});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.nist;
})(globalThis);
