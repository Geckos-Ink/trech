#include "trech/sim/EventRecords.hpp"

#include <filesystem>
#include <fstream>
#include <utility>

namespace trech {

EventRecords::EventRecords(const std::string& outputDir) {
  const std::filesystem::path directory(outputDir);
  paths_ = {(directory / "trech_event_scores.jsonl").string(),
            (directory / "trech_event_features.jsonl").string(),
            (directory / "trech_resim_queue.jsonl").string()};
}

void EventRecords::beginRun(bool ordered) {
  const std::lock_guard<std::mutex> lock(mutex_);
  ordered_ = ordered;
  nextEventId_ = 0;
  pending_.clear();
}

void EventRecords::submit(int eventId, Lines lines) {
  const std::lock_guard<std::mutex> lock(mutex_);
  if (!ordered_) {
    append(lines);
    return;
  }
  pending_.emplace(eventId, std::move(lines));
  while (!pending_.empty() && pending_.begin()->first == nextEventId_) {
    append(pending_.begin()->second);
    pending_.erase(pending_.begin());
    ++nextEventId_;
  }
}

void EventRecords::endRun() {
  const std::lock_guard<std::mutex> lock(mutex_);
  // An aborted run can leave gaps in the assigned event IDs.
  for (const auto& entry : pending_) {
    append(entry.second);
  }
  pending_.clear();
}

void EventRecords::append(const Lines& lines) const {
  const std::array fields{&lines.scores, &lines.features, &lines.resimCandidate};
  for (std::size_t i = 0; i < fields.size(); ++i) {
    if (!fields[i]->empty()) {
      std::ofstream out(paths_[i], std::ios::app);
      out << *fields[i] << '\n';
    }
  }
}

} // namespace trech
