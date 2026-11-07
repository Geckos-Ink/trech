'use strict';
// Build the normalized, offline dataset from the raw cache. Pure function of cached bytes:
// no network, no clock, so the same cache always yields byte-identical dataset JSON.
const fs = require('node:fs');
const path = require('node:path');
const S = require('../lib/index.js');
const {Cache, catalogNames, slug, sha256} = require('./collect.js');

function readJson(cache, key) {
  const hit = cache.read(key);
  if (!hit) return null;
  return {entry: hit.entry, value: hit.entry.status === 200 ? JSON.parse(hit.text) : null, text: hit.text};
}
function sourceRef(hit) { return {url: hit.entry.url, sha256: hit.entry.sha256, fetched_utc: hit.entry.fetched_utc}; }

function buildAtoms(cache, options) {
  const table = readJson(cache, 'pubchem_periodictable.json');
  if (!table || !table.value) throw new Error('periodic table missing from cache; run collect first');
  const [zMin, zMax] = options.elements || [1, 56];
  const facts = {}, atoms = [], rejected = [];
  for (const row of S.pubchem.parsePeriodicTable(table.value)) {
    if (row.z < zMin || row.z > zMax) continue;
    const ground = readJson(cache, 'pubchem_element_' + row.z + '_ground_level.json');
    row.ground_level = ground && ground.value ? S.pubchem.groundLevel(ground.value) : null;
    row.configuration = S.pubchem.parseConfiguration(row.electron_configuration);
    let features = null;
    try { features = S.features.atomicFeatures(row); } catch (error) {
      rejected.push({id: row.symbol, kind: 'atom', reason: String(error.message)});
      continue;
    }
    facts[row.symbol] = {z: row.z, symbol: row.symbol, name: row.name, atomic_mass: row.atomic_mass,
      electron_configuration: row.electron_configuration, ground_level: row.ground_level, electronegativity: row.electronegativity,
      ionization_energy_ev: row.ionization_energy_ev, electron_affinity_ev: row.electron_affinity_ev,
      atomic_radius_pm: row.atomic_radius_pm, group_block: row.group_block, features,
      sources: {periodic_table: sourceRef(table), ground_level: ground ? sourceRef(ground) : null}};
    const spectra = readJson(cache, 'pubchem_element_' + row.z + '_atomic_spectra.json');
    const links = spectra && spectra.value ? S.pubchem.atomicSpectraLinks(spectra.value) : null;
    const id = 'Z' + String(row.z).padStart(3, '0') + '_' + row.symbol;
    if (!links || !links.lines_url) { rejected.push({id, kind: 'atom', reason: 'PubChem record has no NIST ASD lines link'}); continue; }
    const linesHit = cache.read('nist_asd_' + (links.symbol || row.symbol) + '_I_200_1000.csv');
    if (!linesHit) { rejected.push({id, kind: 'atom', reason: 'NIST ASD lines not cached'}); continue; }
    let parsed;
    try { parsed = S.nist.parseLines(linesHit.text); } catch (error) {
      rejected.push({id, kind: 'atom', reason: 'NIST ASD: ' + String(error.message).slice(0, 160)});
      continue;
    }
    const profile = S.grid.atomicProfile(parsed.lines, S.grid.ATOMIC_GRID);
    if (!profile) {
      rejected.push({id, kind: 'atom', reason: 'fewer than ' + S.grid.ATOMIC_GRID.minWeightedLines +
        ' lines with A_ki and g_k in 200-1000 nm (' + parsed.lines.length + ' lines listed)'});
      continue;
    }
    atoms.push({id, z: row.z, symbol: row.symbol, group: row.group_block || 'unknown', features,
      target: profile.target.map(v => Number(v.toFixed(6))),
      lines: {listed: profile.totalLines, weighted: profile.weightedLines, medium: parsed.medium,
        strongest_nm: Number(S.grid.peakWavelength(profile.target, S.grid.ATOMIC_GRID).toFixed(1))},
      sources: {pubchem_atomic_spectra: sourceRef(spectra), pubchem_reference: links.source,
        nist_lines: {url: linesHit.entry.url, sha256: linesHit.entry.sha256, fetched_utc: linesHit.entry.fetched_utc}}});
  }
  return {facts, atoms, rejected};
}

function buildMolecules(cache, catalog, facts) {
  const molecules = [], rejected = [], seen = new Set();
  for (const {name, family} of catalogNames(catalog)) {
    const ids = readJson(cache, 'pubchem_name_' + slug(name) + '.json');
    const reject = reason => rejected.push({id: name, kind: 'molecule', family, reason});
    if (!ids) { reject('not collected'); continue; }
    const cid = ids.value && ids.value.IdentifierList ? ids.value.IdentifierList.CID[0] : null;
    if (!cid) { reject('PubChem name lookup failed'); continue; }
    if (seen.has(cid)) { reject('duplicate CID ' + cid); continue; }
    const props = readJson(cache, 'pubchem_cid_' + cid + '_properties.json');
    const uv = readJson(cache, 'pubchem_cid_' + cid + '_uv.json');
    if (!props || !props.value) { reject('properties missing'); continue; }
    if (!uv || !uv.value) { reject('no PubChem UV Spectra section'); continue; }
    const p = S.pubchem.parseProperties(props.value);
    const statements = S.pubchem.uvStatements(uv.value);
    const chosen = S.pubchem.chooseUv(statements);
    if (!chosen) { reject(statements.length ? 'UV maxima without log epsilon' : 'no parseable absorption-maximum statement'); continue; }
    let graph, analysis;
    try { graph = S.smiles.parse(p.smiles); analysis = S.smiles.analyze(graph); } catch (error) {
      reject('SMILES: ' + String(error.message).slice(0, 120)); continue;
    }
    const unknown = Object.keys(analysis.element_counts).filter(e => analysis.element_counts[e] && !facts[e]);
    if (unknown.length) { reject('element(s) outside atomic fact table: ' + unknown.join(',')); continue; }
    const target = S.grid.molecularEnvelope(chosen.bands, S.grid.MOLECULAR_GRID);
    const inGrid = chosen.bands.filter(b => b.log_epsilon !== null && b.wavelength_nm >= S.grid.MOLECULAR_GRID.start &&
      b.wavelength_nm < S.grid.MOLECULAR_GRID.stop);
    if (!inGrid.length) { reject('all measured maxima outside ' + S.grid.MOLECULAR_GRID.start + '-' + S.grid.MOLECULAR_GRID.stop + ' nm'); continue; }
    seen.add(cid);
    molecules.push({id: 'CID' + cid, cid, name, family, formula: p.formula, smiles: p.smiles, charge: p.charge,
      solvent: chosen.solvent, solvent_class: chosen.solvent_class,
      bands: chosen.bands, target: target.map(v => Number(v.toFixed(6))),
      sources: {uv_text: chosen.raw, uv_reference: chosen.reference, uv: sourceRef(uv), properties: sourceRef(props),
        alternative_statements: statements.length - 1}});
  }
  return {molecules, rejected};
}

function build(options) {
  const cache = new Cache(options.cacheDir, {offline: true});
  const catalog = JSON.parse(fs.readFileSync(options.catalog, 'utf8'));
  const atomic = buildAtoms(cache, options);
  const molecular = buildMolecules(cache, catalog, atomic.facts);
  const dataset = {
    schema: 'trech_spectrum_dataset_v1',
    note: 'Measured reference spectra: NIST ASD neutral-atom line lists reached through PubChem element records, and PubChem (mostly HSDB) UV/Vis absorption maxima. Labels are measurements, not Geant4 output; targets are the declared grid representations.',
    grids: {atomic: S.grid.ATOMIC_GRID, molecular: S.grid.MOLECULAR_GRID},
    feature_sets: {atomic: S.features.ATOMIC_FEATURES, molecular: S.features.MOLECULAR_DESCRIPTORS},
    catalog: {path: path.relative(options.root || process.cwd(), options.catalog), sha256: sha256(fs.readFileSync(options.catalog, 'utf8'))},
    counts: {elements_with_facts: Object.keys(atomic.facts).length, atoms: atomic.atoms.length, molecules: molecular.molecules.length,
      rejected: atomic.rejected.length + molecular.rejected.length},
    element_facts: atomic.facts,
    atoms: atomic.atoms,
    molecules: molecular.molecules,
    rejected: atomic.rejected.concat(molecular.rejected)
  };
  return dataset;
}

module.exports = {build};
