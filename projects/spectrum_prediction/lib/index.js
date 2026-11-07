// Spectrum-prediction shared library loader.
//
// The same sources run on Node.js (data collection, training, validation) and inside the
// TRECH QuickJS host (examples/scenarios/spectrum_prediction), so every module below is
// dependency-free JavaScript that attaches itself to globalThis.TRECH_SPECTRA.
// Node-only work (network, hashing, files) lives in ../src/, never here.
(function (root) {
  'use strict';
  const files = ['./grid.js', './nist.js', './pubchem.js', './smiles.js', './features.js',
    './tensor.js', './models.js', './architectures.js', './validate.js', './export.js'];
  if (typeof module !== 'undefined' && module.exports && typeof require === 'function') {
    require('../../../js/trech_random.js');
    for (const file of files) require(file);
    module.exports = root.TRECH_SPECTRA;
  } else {
    TRECH_INCLUDE('../../../js/trech_random.js');
    for (const file of files) TRECH_INCLUDE(file);
  }
})(globalThis);
