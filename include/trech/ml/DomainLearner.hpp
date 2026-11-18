#pragma once

#include "trech/ml/ComputeBudget.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace trech::ml {

// Online emergence and subdivision of response domains.
//
// A DomainLearner watches a live population: per call it receives element
// features (the context a law could read) and, optionally, the response the
// scenario's own operator produced (the teacher). It keeps a tree of
// half-space splits over the features whose leaves are domains, each with a
// weighted-ridge response model over a polynomial basis (LibTorch batched
// solves). A domain is subdivided where one law cannot explain its rows:
// the split must lower a BIC-penalised error, survive two-fold
// cross-validation and be supported by rows from several calls. Siblings
// whose laws become indistinguishable merge back. Membership is a function of
// the features only, so a frozen learner routes and predicts without targets.
//
// Every prediction is made before the call's rows are learned (prequential),
// and is graded against a pooled single-domain model fed the same rows, so a
// reported gain is out-of-sample. Per domain the learner tracks tendencies:
// exponentially weighted linear trends, forecasts and drift scores of its
// population, feature and target means, prediction error and model
// parameters (raw-unit local sensitivities). A drift in a domain's error
// triggers an immediate subdivision search.
//
// The learner is a predictive-mode diagnostic: it never mutates scenario
// state. Its capacity derives from the ComputeBudget it was created under.
struct DomainLearnerOptions {
  std::vector<std::string> features;  // fixed order
  std::vector<std::string> targets;   // fixed order, may be empty when frozen
  std::size_t minElements = 32;       // rows per side of a split
  std::size_t maxDepth = 6;
  double forgetting = 0.97;           // per-call decay of buffered row weights
  double ridge = 1e-9;                // relative to the mean diagonal
  // Share of a domain's target variance a law may leave unexplained and still
  // count as exact: below it a domain is never split, and siblings whose
  // joint law leaves less merge. It also bounds the smallest useful gain.
  double exactLaw = 1e-6;
  double splitPenalty = 1.0;          // BIC multiplier
  double minGain = 0.05;              // cross-validated relative error reduction
  std::size_t minSupportCalls = 2;    // distinct calls on each side of a split
  std::size_t refineEvery = 1;        // calls between subdivision searches
  std::size_t mergeCooldown = 6;      // calls before a fresh split may merge
  double tendencyDecay = 0.9;         // per-call decay of trend statistics
  double driftZ = 4.0;                // error drift that forces a search
  bool frozen = false;                // route and predict only
  bool tendencyPredictor = true;      // offer ridge+trend (bias tendency) per domain
  std::uint64_t seed = 0;
  LearnerCapacity capacity;
  ComputeBudget budget;               // recorded with the state
};

struct DomainLearnerBatch {
  double time = 0.0;
  std::size_t count = 0;
  std::vector<double> features;  // element-major, options.features order
  std::vector<double> targets;   // element-major or empty
};

struct DomainEvent {
  std::string type;  // birth | split | merge | drift | rescale | model
  int domain = -1;
  std::vector<int> related;
  std::string detail;
};

struct TendencyEstimate {
  std::string series;
  double value = 0.0;     // latest observation
  double level = 0.0;     // trend value at the latest time
  double slope = 0.0;     // per unit time
  double slopeStdErr = 0.0;
  double forecast = 0.0;  // at latest time + horizon
  double forecastStd = 0.0;
  double z = 0.0;         // latest observation against the previous forecast
  std::size_t updates = 0;
  bool significant = false;
};

struct DomainSummary {
  int id = -1;
  std::vector<int> predecessors;
  long bornCall = 0;
  std::size_t depth = 0;
  std::size_t elements = 0;         // rows routed to it this call
  std::size_t bufferRows = 0;
  double effectiveRows = 0.0;
  std::string model;                // none | ridge | ridge+mlp
  std::vector<double> featureMin, featureMax;  // envelope of its buffer
  std::vector<double> valueAtMean;  // per target, raw units
  std::vector<double> sensitivity;  // targets x features, raw units
  std::vector<double> errorRmse;    // prequential EW RMSE per target
  std::vector<double> residualStd;  // in-buffer residual per target
  double extinctionEta = -1.0;      // forecast time to an empty domain, -1 none
  std::vector<TendencyEstimate> tendencies;
};

struct DomainLearnerResult {
  long call = 0;
  std::vector<int> elementDomains;      // after this call's refinement
  std::vector<int> predictionDomains;   // domain that made each prediction
  std::vector<double> predictions;      // element-major, NaN when no model
  std::vector<double> predictionStd;
  std::vector<std::uint8_t> extrapolated;
  std::size_t extrapolatedCount = 0;
  std::size_t scored = 0;               // rows graded prequentially
  std::vector<double> routedRmse;       // per target, this call
  std::vector<double> pooledRmse;       // single-domain baseline, same rows
  std::vector<double> intervalCoverage; // share of graded rows within +-1.96 predictionStd
  std::vector<DomainSummary> domains;   // current leaves, ascending id
  std::vector<DomainEvent> events;
  std::vector<TendencyEstimate> tendencies;  // learner-level series
  double seconds = 0.0;
};

class DomainLearner {
 public:
  explicit DomainLearner(DomainLearnerOptions options);
  ~DomainLearner();
  DomainLearner(DomainLearner&&) noexcept;
  DomainLearner& operator=(DomainLearner&&) noexcept;

  DomainLearnerResult update(const DomainLearnerBatch& batch);
  const DomainLearnerOptions& options() const;
  long calls() const;

  // Models, tree, lineage and options. Buffered rows are data: they are
  // exported only on request, so learning can continue in a later run.
  nlohmann::json exportState(bool includeRows = false) const;
  // Restore an exported learner; `frozen` overrides the stored flag.
  static DomainLearner fromState(const nlohmann::json& state, bool frozen);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace trech::ml
