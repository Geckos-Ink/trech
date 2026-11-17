#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Engine-side ML architecture generation.
//
// Given a named regression job (inputs, outputs, train / selection / optional
// test tables), the engine produces a trained model that GenericSurrogate can
// load, choosing its ARCHITECTURE in one of two ways:
//
//  * classic (always run, in C++): a fixed, documented family of reference
//    structures -- a linear map and SiLU MLPs of depth 1 and 2 at a width set by
//    the problem's widths, the training-set size and the parameter budget --
//    trained by a deterministic native Adam trainer (portable fdlibm math, no
//    FMA contraction, own RNG). The best of them on the selection split is the
//    REFERENCE every generated architecture must beat. It is never a fallback:
//    when Evolvo cannot run or deliver a loadable model the job fails.
//
//  * evolvo (Python worker): the Evolvo GFSL-NN architecture search
//    (thirds/evolvo, papers/GFSL-NN.md) through trech_torch.arch_worker. The
//    classic structures are its seed genomes, so the search starts from the
//    reference and the reference's selection loss travels with the request.
//
// Why a subprocess, not an embedded interpreter: the engine stays buildable and
// linkable without libpython (no ABI coupling, any venv chosen at run time);
// torch threads, memory and crashes stay out of the Geant4 process; the
// boundary is a versioned JSON contract like JS -> JSON -> C++; and strict
// simulation runs never touch it. The bridge is shell-free (posix_spawn), has a
// wall-clock timeout, binds the result to the request by SHA-256, and the
// engine re-scores any JSON model the worker returns on the selection split
// itself instead of trusting the reported loss.
//
// The final choice is made here: Evolvo's architecture is used when its
// selection score ln(loss) + sizeCost * ln(params) is strictly better than the
// classic reference's; otherwise the better model, the reference, is kept
// (status "rejected"). Every other Evolvo outcome sets ok = false with a named
// status and no model. LibTorch is required, so TorchScript results always load.

struct ArchTable {
  // rows x features, in the job's declared input / output order.
  std::vector<std::vector<double>> x;
  std::vector<std::vector<double>> y;
  std::string source;  // file path or "inline", for provenance
  std::size_t rows() const { return y.size(); }
};

struct ArchitectureJob {
  std::string name;
  std::vector<std::string> inputs;
  std::vector<std::string> outputs;
  ArchTable train;
  ArchTable selection;
  ArchTable test;  // optional (no rows -> no carried holdout)
  std::string generator = "evolvo";  // evolvo | classic (classic skips the search)
  std::uint64_t seed = 0;
  // Budgets.
  int maxParams = 50000;
  int maxRows = 6;
  int maxEpochs = 1000;  // hard cap; stopping is a plateau rule
  int generations = 12;
  int population = 10;
  int patience = 4;
  int maxEvaluations = 0;  // 0 = unlimited
  double timeBudgetSeconds = 0.0;
  double workerTimeoutSeconds = 3600.0;
  double sizeCost = 0.03;
  double learningRate = 3e-3;
  std::vector<std::string> ops;  // optional restriction of the GFSL-NN language
  std::string knowledgePath;     // Evolvo knowledge to load and update
  std::string python;            // interpreter override
  // Worker module and extra PYTHONPATH entry (tests swap in fake workers).
  std::string workerModule = "trech_torch.arch_worker";
  std::string workerPath;
  std::string jobPath;              // where the job came from (provenance)
};

// Parse a `trech_arch_job_v1` JSON job. Tables are inline arrays of row
// objects or JSON-lines files (resolved relative to `baseDir`). Throws
// std::invalid_argument naming the first problem.
ArchitectureJob parseArchitectureJob(const nlohmann::json& job, const std::string& baseDir);
ArchitectureJob loadArchitectureJob(const std::string& path);

// One member of the classic reference family.
struct ClassicStructure {
  std::string name;               // "linear", "mlp1", "mlp2"
  std::vector<int> widths;        // hidden widths (empty = linear)
  std::string activation;         // hidden activation ("silu")
  long long params = 0;
  nlohmann::json genome;          // the same structure as an evolvo_arch_genome_v1
};

// The geometric width ladder shared with GFSL-NN: round(2^(k/2)) in [lo, hi].
std::vector<int> widthLadder(int lo, int hi);
// The classic reference family for a job (deterministic, documented rules).
std::vector<ClassicStructure> classicStructures(const ArchitectureJob& job);

struct DenseLayer {
  std::vector<std::vector<double>> weights;  // [out][in]
  std::vector<double> bias;
  std::string activation;                   // silu | tanh | none
};

struct NativeFit {
  ClassicStructure structure;
  std::vector<DenseLayer> layers;
  std::vector<double> xMean, xStd, yMean, yStd;
  double selectionLoss = 0.0;  // MSE in training-standardized outputs
  double score = 0.0;          // ln(loss) + sizeCost * ln(params)
  int epochs = 0;
  int bestEpoch = 0;
  std::string stopReason;
};

// Deterministic full-batch Adam on standardized data, plateau stopping on the
// selection split, best-epoch weights restored.
NativeFit trainClassicNative(const ArchitectureJob& job, const ClassicStructure& structure);
// Raw-unit forward pass of a native fit (the reference the exported JSON must reproduce).
std::vector<double> predictNative(const NativeFit& fit, const std::vector<double>& x);
// generic_surrogate_v1 JSON (scalers, layers, input_domain, test holdout, provenance).
nlohmann::json nativeModelJson(const ArchitectureJob& job, const NativeFit& fit);

struct WorkerRun {
  bool started = false;
  bool timedOut = false;
  int exitCode = -1;
  double seconds = 0.0;
  std::string error;
  std::string logPath;
};

// Spawn `python -m module args...` without a shell; stdout+stderr go to
// `logPath`; PYTHONPATH is prefixed with `pythonPath` entries. POSIX only (on
// Windows it reports started=false and the caller falls back).
WorkerRun runPythonModule(const std::string& python, const std::string& module,
                          const std::vector<std::string>& args,
                          const std::vector<std::string>& pythonPath,
                          const std::string& logPath, double timeoutSeconds);

// Interpreter resolution: job.python, then $TRECH_PYTHON, then the configured
// build default, then "python3" on PATH.
std::string resolvePython(const ArchitectureJob& job);
// Repository root holding tools/torch and thirds/evolvo: $TRECH_ROOT, else the
// configured source directory.
std::string resolveRepositoryRoot();

struct ArchitectureOutcome {
  bool ok = false;               // a loadable model was chosen; false on any Evolvo failure
  std::string generator;         // "evolvo" | "classic" | "none" (failed)
  std::string modelPath;         // the chosen model (JSON or .pt)
  std::string reason;            // why this generator was chosen
  std::string outcomePath;       // <out>/<name>.outcome.json
  nlohmann::json outcome;        // the full trech_arch_outcome_v1 record
};

class ArchitectureGenerator {
 public:
  static ArchitectureOutcome generate(const ArchitectureJob& job, const std::string& outputDir);
};

}  // namespace trech::ml
