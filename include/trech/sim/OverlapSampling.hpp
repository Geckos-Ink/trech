#pragma once

// Geant4-free half of the geometry overlap check. DetectorConstruction samples
// points on every placed solid's surface with this deterministic generator,
// moves them through the real Geant4 placement transforms and asks the real
// Geant4 solids (G4VSolid::Inside / DistanceToIn / DistanceToOut) whether a
// point lies inside a sibling or outside the mother. Geant4's own
// G4PVPlacement::CheckOverlaps draws its surface points from the global CLHEP
// engine; doing so here would shift the run's random stream before the first
// event, so the points come from a private splitmix64 sequence seeded by the
// volume name instead. The check therefore never perturbs a strict replay.

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace trech::sim {

// Shapes DetectorConstruction can build, in half-lengths (mm).
struct OverlapShape {
  enum class Kind { Box, Tube, Sphere };
  Kind kind = Kind::Box;
  double hx = 0.0; // box half-sizes
  double hy = 0.0;
  double hz = 0.0; // box half-size or tube half-length
  double rmin = 0.0; // tube inner radius
  double rmax = 0.0; // tube outer radius or sphere radius
};

struct OverlapCheckSettings {
  int samplesPerVolume = 1000;
  // Overlaps no deeper than this are ignored (Geant4's CheckOverlaps `tol`).
  double toleranceMm = 0.0;
};

// Deterministic 64-bit generator (splitmix64); uniform doubles in [0, 1).
class OverlapRng {
public:
  explicit OverlapRng(std::uint64_t seed) : state_(seed) {}
  std::uint64_t next() {
    std::uint64_t z = (state_ += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
  }
  double uniform() { return static_cast<double>(next() >> 11) * 0x1.0p-53; }

private:
  std::uint64_t state_;
};

// FNV-1a of the volume name, so every volume has its own stable sequence.
inline std::uint64_t overlapSeedFor(const std::string& name) {
  std::uint64_t h = 1469598103934665603ULL;
  for (unsigned char c : name) {
    h ^= c;
    h *= 1099511628211ULL;
  }
  return h;
}

// Surface area of the shape (mm^2); used for area-weighted face choice.
inline double overlapSurfaceArea(const OverlapShape& s) {
  constexpr double kPi = 3.14159265358979323846;
  switch (s.kind) {
  case OverlapShape::Kind::Box:
    return 8.0 * (s.hx * s.hy + s.hy * s.hz + s.hx * s.hz);
  case OverlapShape::Kind::Tube:
    return 2.0 * kPi * (s.rmax + s.rmin) * 2.0 * s.hz +
           2.0 * kPi * (s.rmax * s.rmax - s.rmin * s.rmin);
  case OverlapShape::Kind::Sphere:
    return 4.0 * kPi * s.rmax * s.rmax;
  }
  return 0.0;
}

// `count` points uniformly distributed (by area) on the shape's surface, in the
// solid's local frame.
inline std::vector<std::array<double, 3>> sampleOverlapSurface(const OverlapShape& s, int count,
                                                               std::uint64_t seed) {
  constexpr double kPi = 3.14159265358979323846;
  std::vector<std::array<double, 3>> points;
  if (count <= 0) {
    return points;
  }
  points.reserve(static_cast<std::size_t>(count));
  OverlapRng rng(seed);
  auto signedUnit = [&]() { return 2.0 * rng.uniform() - 1.0; };
  for (int i = 0; i < count; ++i) {
    if (s.kind == OverlapShape::Kind::Box) {
      const double axy = s.hx * s.hy;
      const double ayz = s.hy * s.hz;
      const double axz = s.hx * s.hz;
      const double pick = rng.uniform() * (axy + ayz + axz);
      const double side = rng.uniform() < 0.5 ? -1.0 : 1.0;
      const double u = signedUnit();
      const double v = signedUnit();
      if (pick < axy) {
        points.push_back({u * s.hx, v * s.hy, side * s.hz});
      } else if (pick < axy + ayz) {
        points.push_back({side * s.hx, u * s.hy, v * s.hz});
      } else {
        points.push_back({u * s.hx, side * s.hy, v * s.hz});
      }
    } else if (s.kind == OverlapShape::Kind::Tube) {
      const double outer = 2.0 * kPi * s.rmax * 2.0 * s.hz;
      const double inner = 2.0 * kPi * s.rmin * 2.0 * s.hz;
      const double caps = 2.0 * kPi * (s.rmax * s.rmax - s.rmin * s.rmin);
      const double pick = rng.uniform() * (outer + inner + caps);
      const double phi = 2.0 * kPi * rng.uniform();
      if (pick < outer + inner) {
        const double r = pick < outer ? s.rmax : s.rmin;
        points.push_back({r * std::cos(phi), r * std::sin(phi), signedUnit() * s.hz});
      } else {
        // Uniform on the annulus: r^2 uniform between rmin^2 and rmax^2.
        const double r2 = s.rmin * s.rmin + rng.uniform() * (s.rmax * s.rmax - s.rmin * s.rmin);
        const double r = std::sqrt(r2);
        const double side = rng.uniform() < 0.5 ? -1.0 : 1.0;
        points.push_back({r * std::cos(phi), r * std::sin(phi), side * s.hz});
      }
    } else {
      const double cosTheta = signedUnit();
      const double sinTheta = std::sqrt(std::max(0.0, 1.0 - cosTheta * cosTheta));
      const double phi = 2.0 * kPi * rng.uniform();
      points.push_back({s.rmax * sinTheta * std::cos(phi), s.rmax * sinTheta * std::sin(phi),
                        s.rmax * cosTheta});
    }
  }
  return points;
}

} // namespace trech::sim
