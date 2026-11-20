#pragma once

#include "trech/ml/DomainLearner.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Engine-wide statistical arbitration among prediction METHODS.
//
// Any engine path that owns more than one way to predict the same quantity (algorithmic
// methods such as lattice Boltzmann, learned operators, surrogate networks, baselines such as
// persistence, and any method added later) hands its candidates' predictions to a
// MethodArbiter. The arbiter names no physics, scenario or domain: it sees elements, their
// context features and one prediction per method per element (NaN = the method abstains for
// that element). One DomainLearner per method learns that method's error over the context,
// from the elements the method predicted; the method with the lowest PREDICTED error is
// selected per element, so the best method emerges per context domain from evidence instead
// of being chosen by a caller or a textbook threshold.
//
// Prequential discipline: errors are predicted before the call's reference is learned. Calls
// without a reference are selected from the learned errors too (deployment); they teach nothing.
// The learned selection must earn its use: the arbiter scores two policies on every graded call
// (decayed log-ratio of their call errors, and decayed total squared error), the learned
// per-domain selection and the recent leader (the method
// with the lowest decayed mean log call error, else the declared fallback), and applies the learned
// one only while it has been better on both scores. Within the learned policy an element leaves the leader
// only when the predicted log-error advantage exceeds the two error learners' own prequential
// log-RMSE (hysteresis set by evidence, not a constant). Before any evidence distinguishes the methods, the lower
// median of the candidates' distinct predictions is used (a prior that privileges no method). Errors are learned as log(error + 1e-6 x scale). A method
// with a non-finite prediction for an element is not a candidate for that element.
struct MethodArbiterOptions {
  std::vector<std::string> methods;   // candidate names, fixed order (at least one)
  std::vector<std::string> features;  // context feature names, fixed order (at least one)
  std::size_t outputs = 1;            // values per element and method
  std::string fallback;               // method used before any evidence; empty = the first
  std::size_t minElements = 32;       // learner rows per split side
  double forgetting = 0.97;           // per-call decay of the learner's buffered rows
  double policyForgetting = 0.8;      // per-call decay of the policy and leader scores (phases)
  std::uint64_t seed = 0;
};

struct MethodArbiterBatch {
  double time = 0.0;
  std::size_t count = 0;
  std::vector<double> features;     // element-major, options.features order
  std::vector<double> predictions;  // element-major: [element][method][output]
  std::vector<double> reference;    // [element][output], empty when ungraded; NaN skips an element
  std::vector<double> scale;        // per output scale (sets the 1e-6 error floor), empty = 1
};

struct MethodArbiterResult {
  std::vector<int> selection;           // per element: method index, -1 when no method predicts it
  std::vector<std::uint8_t> learned;    // 1 when chosen from learned (predicted) errors
  std::vector<double> value;            // [element][output] of the selected method
  std::vector<double> predictedError;   // [element][method], NaN when no law yet
  std::string policy;                   // "learned_domains", "recent_leader" or "candidate_median"
  std::string leader;                   // method with the lowest decayed realized error
  bool graded = false;
  std::size_t gradedElements = 0;      // elements with a finite reference and a selection
  std::vector<double> callRmse;         // per method, this call, on the elements it predicted
  double arbitratedRmse = 0.0, oracleRmse = 0.0;
  nlohmann::json report;                // learner call: domains with their winning method
};

class MethodArbiter {
 public:
  explicit MethodArbiter(MethodArbiterOptions options);
  ~MethodArbiter();
  MethodArbiter(MethodArbiter&&) noexcept;
  MethodArbiter& operator=(MethodArbiter&&) noexcept;

  MethodArbiterResult step(const MethodArbiterBatch& batch);
  // Run totals: per method the RMSE on its own elements, on the elements every method predicted
  // (rmse_common, the fair comparison), its coverage and selected share; the best single method
  // (on common elements); the arbitrated and oracle (best per element) RMSE; the learned
  // selection and policy shares; each method's latest error domains; three phase windows.
  nlohmann::json summary() const;
  // The graded calls split into equal consecutive windows (phases): per window, each method's
  // RMSE and selected share, the arbitrated and oracle RMSE and the best single method. A later
  // window is out-of-sample time for everything learned before it.
  nlohmann::json phases(std::size_t windows) const;
  const MethodArbiterOptions& options() const;

  // Learned state: options, each method's error learner, the leader and policy scores, and
  // the evidence flag (`trech_method_arbiter_v1`). Run totals and phase history are not part
  // of it, so a restored arbiter reports only its new run. Buffered learner rows are data and
  // are exported only on request.
  nlohmann::json exportState(bool includeRows = false) const;
  // Restore an exported arbiter. A frozen one selects from what it learned and grades graded
  // calls in its summary (the held-out test of the choice), but learns nothing.
  static MethodArbiter fromState(const nlohmann::json& state, bool frozen);
  bool frozen() const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace trech::ml
