'use strict';
// Network collection with a content-addressed, build-local cache (Node.js >= 18, global fetch).
//
// Atoms:     PubChem periodic table -> PubChem element "Atomic Spectra" + "Ground Level" sections
//            -> the NIST ASD line list PubChem points to (neutral spectrum, 200-1000 nm CSV).
// Molecules: PubChem name -> CID -> properties (SMILES/formula) -> PUG-View "UV Spectra".
//
// Every response is stored verbatim with its URL, UTC fetch time, HTTP status and SHA-256 in
// <cache>/manifest.json. --offline never touches the network; a missing entry is an error that
// the dataset builder records as a rejection instead of substituting data.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const S = require('../lib/index.js');

const PUG = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug';
const PUG_VIEW = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data';
const USER_AGENT = 'TRECH-spectrum-prediction/0.1 (research cache; https://pubchem.ncbi.nlm.nih.gov/docs/programmatic-access)';
const DELAY_MS = {pubchem: 230, nist: 900};

function sha256(text) { return crypto.createHash('sha256').update(text).digest('hex'); }
function slug(text) { return String(text).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 80); }
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

class Cache {
  constructor(dir, options) {
    this.dir = dir;
    this.offline = !!(options && options.offline);
    this.refresh = !!(options && options.refresh);
    this.log = (options && options.log) || (() => {});
    fs.mkdirSync(path.join(dir, 'raw'), {recursive: true});
    this.manifestPath = path.join(dir, 'manifest.json');
    this.manifest = fs.existsSync(this.manifestPath) ? JSON.parse(fs.readFileSync(this.manifestPath, 'utf8'))
      : {schema: 'trech_spectrum_cache_v1', entries: {}};
    this.lastRequest = {};
    this.fetched = 0;
  }
  save() { fs.writeFileSync(this.manifestPath, JSON.stringify(this.manifest, null, 1) + '\n'); }
  has(key) { return !!this.manifest.entries[key] && fs.existsSync(path.join(this.dir, 'raw', key)); }
  read(key) {
    const entry = this.manifest.entries[key];
    if (!entry || !fs.existsSync(path.join(this.dir, 'raw', key))) return null;
    const text = fs.readFileSync(path.join(this.dir, 'raw', key), 'utf8');
    if (sha256(text) !== entry.sha256) throw new Error('cache entry ' + key + ' does not match its recorded SHA-256');
    return {text, entry};
  }
  // Returns {text, entry}; HTTP 4xx responses are cached too (PubChem answers 404/400 for
  // "no such heading"), so absence is recorded once instead of re-queried.
  async get(key, url, host) {
    if (!this.refresh) { const hit = this.read(key); if (hit) return hit; }
    if (this.offline) throw new Error('offline: no cached response for ' + key);
    for (let attempt = 0; attempt < 4; attempt++) {
      const wait = (this.lastRequest[host] || 0) + DELAY_MS[host] - Date.now();
      if (wait > 0) await sleep(wait);
      this.lastRequest[host] = Date.now();
      let response;
      try {
        response = await fetch(url, {headers: {'User-Agent': USER_AGENT, Accept: '*/*'}});
      } catch (error) {
        this.log({event: 'retry', key, reason: String(error.message || error)});
        await sleep(1500 * (attempt + 1));
        continue;
      }
      const text = await response.text();
      if (response.status === 503 || response.status === 429 || response.status >= 500) {
        this.log({event: 'retry', key, status: response.status});
        await sleep(2500 * (attempt + 1));
        continue;
      }
      fs.writeFileSync(path.join(this.dir, 'raw', key), text);
      const entry = {url, status: response.status, fetched_utc: new Date().toISOString(), sha256: sha256(text),
        bytes: Buffer.byteLength(text)};
      this.manifest.entries[key] = entry;
      this.fetched++;
      if (this.fetched % 20 === 0) this.save();
      return {text, entry};
    }
    throw new Error('giving up on ' + url);
  }
}

function json(hit) {
  try { return JSON.parse(hit.text); } catch (e) { throw new Error('non-JSON response for ' + hit.entry.url); }
}

async function collectAtoms(cache, options) {
  const [zMin, zMax] = options.elements || [1, 56];
  const table = await cache.get('pubchem_periodictable.json', PUG + '/periodictable/JSON', 'pubchem');
  const elements = S.pubchem.parsePeriodicTable(json(table)).filter(e => e.z >= zMin && e.z <= zMax);
  const report = [];
  for (const element of elements) {
    const item = {z: element.z, symbol: element.symbol};
    try {
      const spectra = await cache.get('pubchem_element_' + element.z + '_atomic_spectra.json',
        PUG_VIEW + '/element/' + element.z + '/JSON?heading=Atomic+Spectra', 'pubchem');
      await cache.get('pubchem_element_' + element.z + '_ground_level.json',
        PUG_VIEW + '/element/' + element.z + '/JSON?heading=Ground+Level', 'pubchem');
      const links = spectra.entry.status === 200 ? S.pubchem.atomicSpectraLinks(json(spectra)) : null;
      if (!links || !links.lines_url) { item.status = 'no_pubchem_atomic_spectra_link'; report.push(item); continue; }
      const symbol = links.symbol || element.symbol;
      const lines = await cache.get('nist_asd_' + symbol + '_I_200_1000.csv', S.nist.linesUrl(symbol, 200, 1000), 'nist');
      item.status = 'ok';
      item.bytes = lines.entry.bytes;
    } catch (error) {
      item.status = 'error';
      item.error = String(error.message || error);
    }
    report.push(item);
    options.log({event: 'atom', z: element.z, symbol: element.symbol, status: item.status});
  }
  return report;
}

function catalogNames(catalog) {
  const out = [];
  for (const family of Object.keys(catalog.families)) for (const name of catalog.families[family]) out.push({name, family});
  return out;
}

async function collectMolecules(cache, catalog, options) {
  const report = [];
  const properties = 'MolecularFormula,MolecularWeight,SMILES,ConnectivitySMILES,IUPACName,Charge';
  for (const {name, family} of catalogNames(catalog)) {
    const item = {name, family};
    try {
      const ids = await cache.get('pubchem_name_' + slug(name) + '.json',
        PUG + '/compound/name/' + encodeURIComponent(name) + '/cids/JSON', 'pubchem');
      const cid = ids.entry.status === 200 ? (json(ids).IdentifierList || {CID: []}).CID[0] : null;
      if (!cid) { item.status = 'name_not_found'; report.push(item); continue; }
      item.cid = cid;
      await cache.get('pubchem_cid_' + cid + '_properties.json', PUG + '/compound/cid/' + cid + '/property/' + properties + '/JSON', 'pubchem');
      const uv = await cache.get('pubchem_cid_' + cid + '_uv.json', PUG_VIEW + '/compound/' + cid + '/JSON?heading=UV+Spectra', 'pubchem');
      item.status = uv.entry.status === 200 ? 'ok' : 'no_uv_section';
    } catch (error) {
      item.status = 'error';
      item.error = String(error.message || error);
    }
    report.push(item);
    options.log({event: 'molecule', name, cid: item.cid || null, status: item.status});
  }
  return report;
}

async function collect(options) {
  const cache = new Cache(options.cacheDir, options);
  const catalog = JSON.parse(fs.readFileSync(options.catalog, 'utf8'));
  try {
    const atoms = options.skipAtoms ? [] : await collectAtoms(cache, options);
    const molecules = options.skipMolecules ? [] : await collectMolecules(cache, catalog, options);
    return {atoms, molecules, fetched: cache.fetched};
  } finally {
    cache.save();
  }
}

module.exports = {Cache, collect, catalogNames, slug, sha256, PUG, PUG_VIEW};
