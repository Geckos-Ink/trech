// TRECH_TRACE outside the TRECH engine: the same logging and tracing API for host-neutral
// JavaScript (model definitions, domain libraries, tools) when it runs in plain Node or in a
// Node VM sandbox.
//
// Inside `trech` (QuickJS or V8) the engine installs TRECH_TRACE and console itself, and this
// file only returns that object: TRECH_INCLUDE("trech_trace.js") is a no-op there. In Node:
//
//   const TRECH_TRACE = require('../../js/trech_trace.js');      // installs globalThis.TRECH_TRACE
//   TRECH_TRACE.channel('atomic').info('solved', { n: 3 });
//
// configured from the same environment as the engine: TRECH_TRACE=<level>[:<cat>,...],
// TRECH_TRACE_FILE=<path> (JSONL, schema trech_trace_v1) and TRECH_TRACE_STDERR=1 (one line per
// record on stderr; the default when no file is set). warn/error always reach stderr.
// createTrace({level, categories, sink}) builds an isolated instance (used by the model loader
// to collect a definition file's logs). Nothing here feeds wall time or state back to callers.
(function(root) {
  'use strict';
  var LEVELS = { off: 0, summary: 1, info: 2, debug: 3, trace: 4 };

  function parseLevel(name) {
    var key = String(name === undefined || name === null ? '' : name).trim().toLowerCase();
    if (key === '' || key === 'on' || key === 'true') return 'info';
    if (key === 'none' || key === 'false' || key === '0') return 'off';
    if (key === 'all') return 'trace';
    if (/^[1-4]$/.test(key)) return ['off', 'summary', 'info', 'debug', 'trace'][Number(key)];
    if (!Object.prototype.hasOwnProperty.call(LEVELS, key)) {
      throw new Error("unknown trace level '" + name + "' (expected off, summary, info, debug or trace)");
    }
    return key;
  }

  function parseSpec(spec) {
    var text = String(spec || '');
    var colon = text.indexOf(':');
    var level = parseLevel(colon < 0 ? text : text.slice(0, colon));
    var categories = colon < 0 ? [] : text.slice(colon + 1).split(',').map(function(c) { return c.trim(); })
      .filter(function(c) { return c.length > 0; });
    return { level: level, categories: categories };
  }

  function text(value) {
    if (typeof value === 'string') return value;
    if (value === undefined) return 'undefined';
    if (value !== null && typeof value === 'object') {
      try { return JSON.stringify(value); } catch (e) { return String(value); }
    }
    return String(value);
  }

  // options: {level, categories, sink(record), loud(record), host}
  function createTrace(options) {
    var opts = options || {};
    var level = parseLevel(opts.level === undefined ? 'off' : opts.level);
    var categories = opts.categories || [];
    var sink = opts.sink || function() {};
    var loud = opts.loud || function() {};
    var seq = 0;
    var counters = Object.create(null);
    var authored = Object.create(null);

    function enabled(wanted, category) {
      var w = LEVELS[parseLevel(wanted === undefined ? 'info' : wanted)] || LEVELS.info;
      if (LEVELS[level] < w) return false;
      return categories.length === 0 || categories.indexOf(String(category)) >= 0;
    }
    function record(lvl, category, message, data, severity) {
      var rec = { schema: 'trech_trace_v1', seq: 0, level: lvl, cat: category, msg: text(message) };
      if (severity) rec.severity = severity;
      if (data !== undefined) rec.data = JSON.parse(JSON.stringify(data === undefined ? null : data));
      if (!enabled(lvl, category)) {
        if (severity === 'warn' || severity === 'error') loud(rec);
        return;
      }
      rec.seq = ++seq;
      sink(rec);
    }
    function channel(category) {
      category = String(category === undefined ? 'script' : category);
      function at(lvl, severity) { return function(message, data) { record(lvl, category, message, data, severity); }; }
      return {
        category: category,
        info: at('info', ''), log: at('info', ''), debug: at('debug', ''), trace: at('trace', ''),
        warn: at('info', 'warn'), error: at('info', 'error'),
        enabled: function(lvl) { return enabled(lvl === undefined ? 'info' : lvl, category); },
        count: function(name, amount) {
          if (level === 'off') return;
          var key = category + '.' + String(name);
          counters[key] = (counters[key] || 0) + (amount === undefined ? 1 : Number(amount));
        },
        span: function(name, fn, data) {
          if (typeof fn !== 'function') throw new TypeError('TRECH_TRACE.span(name, fn) needs a function');
          if (!enabled('debug', category)) return fn();
          var start = Date.now();
          try { return fn(); } finally {
            var payload = { span: String(name), duration_ms: Date.now() - start };
            if (data !== undefined) payload.data = data;
            record('debug', category, String(name), payload, '');
          }
        }
      };
    }
    var api = channel('script');
    api.channel = function(category) { return Object.freeze(channel(category)); };
    api.level = function() { return level; };
    api.authored = function(law, detail) {
      if (level === 'off') return;
      var name = String(law === undefined ? 'unnamed' : law);
      authored[name] = (authored[name] || 0) + 1;
      record('debug', 'authored', name, detail, '');
    };
    api.host = opts.host || 'node';
    // Counters and authored-law counts so far (the Node analogue of the engine's run summary).
    api.summary = function() {
      return JSON.parse(JSON.stringify({ counters: counters, authored: authored }));
    };
    api.createTrace = createTrace;
    api.parseSpec = parseSpec;
    return Object.freeze(api);
  }

  function fromEnvironment() {
    var env = (typeof process !== 'undefined' && process.env) || {};
    var spec = parseSpec(env.TRECH_TRACE || 'off');
    var file = env.TRECH_TRACE_FILE || '';
    var toStderr = Boolean(env.TRECH_TRACE_STDERR && !/^(0|false|off)$/i.test(env.TRECH_TRACE_STDERR)) || !file;
    var fs = null;
    if (file && typeof require === 'function') fs = require('node:fs');
    function line(rec) {
      var where = rec.cat + (rec.severity ? ' ' + rec.severity : '');
      return '[trech:' + rec.level + '] ' + where + ' ' + rec.msg + (rec.data !== undefined ? ' ' + JSON.stringify(rec.data) : '');
    }
    return createTrace({
      level: spec.level,
      categories: spec.categories,
      host: 'node',
      sink: function(rec) {
        if (fs) fs.appendFileSync(file, JSON.stringify(rec) + '\n');
        if (toStderr && typeof process !== 'undefined') process.stderr.write(line(rec) + '\n');
      },
      loud: function(rec) {
        if (typeof process !== 'undefined') process.stderr.write('TRECH js ' + rec.severity + ': ' + rec.msg +
          (rec.data !== undefined ? ' ' + JSON.stringify(rec.data) : '') + '\n');
      }
    });
  }

  // Inside trech the engine's TRECH_TRACE already exists (host "trech"); keep it.
  var trace = root.TRECH_TRACE || fromEnvironment();
  if (!root.TRECH_TRACE) root.TRECH_TRACE = trace;
  // Node: the frozen API itself (it also carries createTrace and parseSpec).
  if (typeof module !== 'undefined' && module.exports) module.exports = root.TRECH_TRACE.createTrace
    ? root.TRECH_TRACE : Object.assign({}, root.TRECH_TRACE, { createTrace: createTrace, parseSpec: parseSpec });
  return trace;
})(globalThis);
