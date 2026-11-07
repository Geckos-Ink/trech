// PubChem record parsers: periodic-table facts, element "Atomic Spectra"/"Ground Level"
// sections, compound properties and measured UV/Vis absorption-maximum statements.
//
// The UV parser is deliberately strict: a band is accepted only when the text states a
// wavelength in nm next to an explicit "log e"/"log epsilon" value, or (wavelength-only) inside
// an absorption-maximum statement. Collection catalogue numbers (e.g. "UV: 89 (Sadtler ...)"),
// E1%/1cm values and prose ranges are rejected rather than reinterpreted.
(function (root) {
  'use strict';
  const S = root.TRECH_SPECTRA = root.TRECH_SPECTRA || {};

  function num(text) {
    if (text === undefined || text === null || String(text).trim() === '') return null;
    const v = Number(String(text).trim());
    return Number.isFinite(v) ? v : null;
  }

  // https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/JSON
  function parsePeriodicTable(json) {
    const table = json && json.Table;
    if (!table || !table.Columns || !Array.isArray(table.Row)) throw new Error('Not a PubChem periodic-table response');
    const cols = table.Columns.Column;
    return table.Row.map(row => {
      const cell = name => row.Cell[cols.indexOf(name)];
      return {z: num(cell('AtomicNumber')), symbol: cell('Symbol'), name: cell('Name'),
        atomic_mass: num(cell('AtomicMass')), electron_configuration: cell('ElectronConfiguration') || null,
        electronegativity: num(cell('Electronegativity')), atomic_radius_pm: num(cell('AtomicRadius')),
        ionization_energy_ev: num(cell('IonizationEnergy')), electron_affinity_ev: num(cell('ElectronAffinity')),
        group_block: cell('GroupBlock') || null, standard_state: cell('StandardState') || null};
    });
  }

  function strings(section, out) {
    out = out || [];
    for (const info of (section && section.Information) || []) {
      const value = info.Value || {};
      for (const markup of value.StringWithMarkup || [])
        out.push({text: markup.String, url: info.URL || null, reference: info.ReferenceNumber || null, name: info.Name || null});
    }
    for (const child of (section && section.Section) || []) strings(child, out);
    return out;
  }
  function references(json) {
    const map = {};
    for (const ref of (json && json.Record && json.Record.Reference) || [])
      map[ref.ReferenceNumber] = {source: ref.SourceName || null, name: ref.Name || null, url: ref.URL || null,
        license: ref.LicenseURL || null};
    return map;
  }
  function recordStrings(json) {
    if (!json || !json.Record) {
      const fault = json && json.Fault;
      throw new Error('PubChem PUG-View response without Record' + (fault ? ': ' + fault.Message : ''));
    }
    return strings(json.Record);
  }

  // Element "Atomic Spectra" section -> NIST ASD pointers (the provenance chain for atomic lines).
  function atomicSpectraLinks(json) {
    const refs = references(json);
    const out = {lines_url: null, levels_url: null, source: null, symbol: null};
    for (const s of recordStrings(json)) {
      if (!s.url) continue;
      if (/lines/i.test(s.text) || /lines_hold/.test(s.url)) out.lines_url = s.url;
      if (/levels/i.test(s.text) || /levels_hold/.test(s.url)) out.levels_url = s.url;
      const m = /[?&]el=([A-Za-z]+)/.exec(s.url);
      if (m) out.symbol = m[1];
      if (s.reference && refs[s.reference]) out.source = refs[s.reference];
    }
    return out;
  }

  // "3P0", "2S1/2", "5D4", "4S°3/2" -> {multiplicity, L, J, odd}.
  function parseGroundLevel(text) {
    const m = /^\s*(\d+)\s*([SPDFGHIKLMNOQ])\s*([°*o]?)\s*(\d+(?:\/\d+)?)\s*$/.exec(String(text || ''));
    if (!m) return null;
    const L = 'SPDFGHIKLMNOQ'.indexOf(m[2]);
    const parts = m[4].split('/');
    const J = parts.length === 2 ? Number(parts[0]) / Number(parts[1]) : Number(parts[0]);
    return {term: m[0].trim(), multiplicity: Number(m[1]), L, J, odd: !!m[3]};
  }
  function groundLevel(json) {
    for (const s of recordStrings(json)) {
      const parsed = parseGroundLevel(s.text);
      if (parsed) return parsed;
    }
    return null;
  }

  // "[Ar]4s2 3d10 4p1" -> valence subshell occupation outside the bracketed core.
  function parseConfiguration(text) {
    if (!text) return null;
    const body = String(text).replace(/\[[A-Za-z]+\]/g, ' ');
    const out = {s: 0, p: 0, d: 0, f: 0, n_max: 0, subshells: []};
    const re = /(\d+)([spdf])(\d+)/g;
    let m, found = false;
    while ((m = re.exec(body))) {
      found = true;
      const n = Number(m[1]), occ = Number(m[3]);
      out[m[2]] += occ;
      out.n_max = Math.max(out.n_max, n);
      out.subshells.push({n, l: m[2], electrons: occ});
    }
    if (!found) return null;
    const core = /\[([A-Za-z]+)\]/.exec(String(text));
    out.core = core ? core[1] : null;
    return out;
  }

  // Compound property table row -> normalized facts.
  function parseProperties(json) {
    const row = json && json.PropertyTable && json.PropertyTable.Properties && json.PropertyTable.Properties[0];
    if (!row || !row.CID) throw new Error('PubChem property response without CID');
    return {cid: row.CID, formula: row.MolecularFormula || null, molecular_weight: num(row.MolecularWeight),
      smiles: row.SMILES || row.IsomericSMILES || row.ConnectivitySMILES || row.CanonicalSMILES || null,
      connectivity_smiles: row.ConnectivitySMILES || row.CanonicalSMILES || null,
      iupac_name: row.IUPACName || null, charge: row.Charge === undefined ? null : Number(row.Charge)};
  }

  const SOLVENTS = [
    [/\b(alcohol|alc|ethanol|etoh|methanol|meoh|propanol|isopropanol|butanol)\b/i, 'protic'],
    [/\b(water|aqueous|aq|h2o|acid|hcl|naoh|buffer|base)\b/i, 'protic'],
    [/\b(acetonitrile|dioxane|ether|thf|tetrahydrofuran|dmso|dimethylformamide|dmf|acetone)\b/i, 'aprotic'],
    [/\b(hexane|cyclohexane|heptane|isooctane|pentane|octane|petroleum|benzene|carbon tetrachloride|ccl4|chloroform|dichloromethane|methylene chloride|toluene|vapou?r|gas)\b/i, 'nonpolar']
  ];
  function solventClass(text) {
    if (!text) return 'unknown';
    for (const [re, cls] of SOLVENTS) if (re.test(text)) return cls;
    return 'unknown';
  }

  const LOG_E = '(?:log\\s*(?:epsilon|eps|e(?![a-z])|ε)\\.?\\s*[=:]?\\s*)';
  // "243 NM (LOG E= 2.2)"; inside a maximum statement the unit may be omitted ("219 (LOG E= 3.89)").
  const PAIR = new RegExp('(?<![\\d.])(\\d{2,4}(?:\\.\\d+)?)\\s*nm\\b[^;,()]{0,24}?\\(?\\s*' + LOG_E + '(\\d(?:\\.\\d+)?)\\s*\\)?', 'gi');
  const PAIR_NO_UNIT = new RegExp('(?<![\\d.])(\\d{3}(?:\\.\\d+)?)\\s*(?:shoulder\\s*)?\\(\\s*' + LOG_E + '(\\d(?:\\.\\d+)?)\\s*\\)', 'gi');
  // "log epsilon = 3.25 at 290 nm"
  const PAIR_REVERSED = new RegExp(LOG_E + '(\\d(?:\\.\\d+)?)\\s*at\\s*(\\d{3}(?:\\.\\d+)?)\\s*nm\\b', 'gi');
  const BARE = /(?<![\d.])(\d{2,4}(?:\.\d+)?)\s*nm\b/gi;
  // Linear molar absorptivity: "250 nm (epsilon 13800)", "247 NM (E= 14,500)", "(e = 6756)",
  // "(molar extinction coefficient = 36,400 ...)". Specific absorbance E(1%, 1 cm) is rejected.
  const EPS = '(?:epsilon|ε|e|molar extinction coefficient)';
  const LINEAR = new RegExp('(?<![\\d.])(\\d{3}(?:\\.\\d+)?)\\s*nm\\s*\\(([^)]*)\\)', 'gi');
  const LINEAR_VALUE = new RegExp('^\\s*' + EPS + '\\s*(?:about\\s*|=\\s*|:\\s*)*(\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?(?![\\d%])', 'i');
  // Lists: "230, 260, 319 nm (epsilon = 20,800, 16,200, 6,290)".
  const LIST = new RegExp('((?:\\d{3}(?:\\.\\d+)?\\s*,\\s*)+\\d{3}(?:\\.\\d+)?)\\s*nm\\s*\\(\\s*' + EPS + '\\s*[=:]?\\s*([^)]*)\\)', 'gi');
  function specificAbsorbance(text) { return /%|a\s*1|1\s*cm|e\s*\(1/i.test(text); }
  // Parse one PubChem UV text statement. Returns null when it is not an absorption-maximum record.
  function parseUvStatement(text) {
    const raw = String(text || '');
    const isMax = /(max(?:imum|ima)?\.?\s*(?:uv\s*)?(?:absorption|abs)|absorption\s*max|λ\s*max|lambda\s*max|uv\s*max)/i.test(raw);
    if (!isMax && !/log\s*(?:epsilon|e(?![a-z])|ε)/i.test(raw)) return null;
    const solventMatch = /\(([^)]*)\)\s*:/.exec(raw) || /\bin\s+([a-z][a-z \-]+?)(?:\s+at|\s*[:;,.]|$)/i.exec(raw);
    const solvent = solventMatch ? solventMatch[1].trim() : null;
    const bands = [], seen = new Set();  // seen: wavelengths already taken
    let m;
    const accept = (wl, le, text, index) => {
      if (!(wl >= 150 && wl <= 1000) || !(le > 0 && le < 7) || seen.has(wl)) return;
      bands.push({wavelength_nm: wl, log_epsilon: le, shoulder: /shoulder|sh\b|inflection|infl/i.test(text)});
      seen.add(wl);
    };
    PAIR.lastIndex = 0;
    while ((m = PAIR.exec(raw))) accept(Number(m[1]), Number(m[2]), m[0]);
    PAIR_REVERSED.lastIndex = 0;
    while ((m = PAIR_REVERSED.exec(raw))) accept(Number(m[2]), Number(m[1]), m[0]);
    if (isMax && !bands.length) {
      LIST.lastIndex = 0;
      while ((m = LIST.exec(raw))) {
        if (specificAbsorbance(m[2])) continue;
        const wls = m[1].split(/\s*,\s*/).map(Number);
        const eps = m[2].split(/,\s+|;\s*/).map(v => Number(v.replace(/,/g, '')));
        if (wls.length !== eps.length || eps.some(v => !(v >= 1 && v <= 1e6))) continue;
        wls.forEach((wl, i) => accept(wl, Math.log10(eps[i]), m[0]));
      }
      LINEAR.lastIndex = 0;
      while ((m = LINEAR.exec(raw))) {
        if (specificAbsorbance(m[2])) continue;
        const v = LINEAR_VALUE.exec(m[2]);
        if (!v) continue;
        const eps = Number(v[1].replace(/,/g, ''));
        if (eps >= 1 && eps <= 1e6) accept(Number(m[1]), Math.log10(eps), m[0]);
      }
    }
    if (isMax && !bands.length) {
      PAIR_NO_UNIT.lastIndex = 0;
      while ((m = PAIR_NO_UNIT.exec(raw))) accept(Number(m[1]), Number(m[2]), m[0]);
    }
    if (isMax && !bands.length) {
      // Wavelength-only maxima ("UV max = 276 nm"). Ranges ("453 nm to 456 nm") are rejected.
      if (/\bto\b|\-\s*\d+\s*nm|between/i.test(raw)) return null;
      BARE.lastIndex = 0;
      while ((m = BARE.exec(raw))) {
        const wl = Number(m[1]);
        if (wl >= 150 && wl <= 1000) bands.push({wavelength_nm: wl, log_epsilon: null, shoulder: false});
      }
    }
    if (!bands.length) return null;
    bands.sort((a, b) => a.wavelength_nm - b.wavelength_nm);
    return {raw, solvent, solvent_class: solventClass(solvent || raw), bands,
      with_epsilon: bands.filter(b => b.log_epsilon !== null).length};
  }

  function uvStatements(json) {
    const refs = references(json);
    return recordStrings(json).map(s => {
      const parsed = parseUvStatement(s.text);
      if (!parsed) return null;
      parsed.reference = s.reference && refs[s.reference] ? refs[s.reference] : null;
      return parsed;
    }).filter(Boolean);
  }
  // Prefer the statement with the most epsilon-bearing bands; ties prefer protic (alcohol) solvents.
  function chooseUv(statements) {
    const rank = s => s.with_epsilon * 10 + (s.solvent_class === 'protic' ? 1 : 0);
    const usable = statements.filter(s => s.with_epsilon > 0);
    if (!usable.length) return null;
    return usable.slice().sort((a, b) => rank(b) - rank(a))[0];
  }

  S.pubchem = Object.freeze({parsePeriodicTable, atomicSpectraLinks, parseGroundLevel, groundLevel,
    parseConfiguration, parseProperties, parseUvStatement, uvStatements, chooseUv, solventClass, recordStrings});
  if (typeof module !== 'undefined' && module.exports) module.exports = S.pubchem;
})(globalThis);
