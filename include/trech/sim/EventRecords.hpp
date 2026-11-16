#pragma once

#include <array>
#include <map>
#include <mutex>
#include <string>

namespace trech {

// Shared by the master and worker actions for one Geant4 kernel.
class EventRecords {
public:
  struct Lines {
    std::string scores;
    std::string features;
    std::string resimCandidate;
  };

  explicit EventRecords(const std::string& outputDir);
  void beginRun(bool ordered);
  void submit(int eventId, Lines lines);
  void endRun();

private:
  void append(const Lines& lines) const;

  std::mutex mutex_;
  std::array<std::string, 3> paths_;
  bool ordered_ = false;
  int nextEventId_ = 0;
  std::map<int, Lines> pending_;
};

} // namespace trech
