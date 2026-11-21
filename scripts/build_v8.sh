#!/usr/bin/env bash
# Build V8 from source for TRECH: the pinned thirds/v8 submodule as one static library
# (obj/libv8_monolith.a) that CMake links with -DTRECH_V8_BUILD_DIR=<out dir>.
#
# Use it when no packaged V8 fits: another platform or architecture, a pinned revision for
# reproducible builds, a debug V8, or a static binary without V8 shared libraries.
# On macOS, `brew install v8` is the quick alternative (docs/engine/v8.md).
#
# This is the heavy upstream workflow: it downloads depot_tools and V8's dependencies
# (several GB) and compiles for a long time. TRECH's own build never runs it.
#
# Usage:
#   scripts/build_v8.sh [--out <dir>] [--depot-tools <dir>] [--jobs <n>] [--debug]
#                       [--no-sync] [--gn-args '<extra args>']
# Defaults: --out thirds/v8/out.gn/trech, --depot-tools build/depot_tools.
#
# Then configure TRECH:
#   cmake -S . -B build/v8 -DTRECH_ENABLE_V8=ON -DTRECH_V8_BUILD_DIR=$PWD/thirds/v8/out.gn/trech
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
v8="$root/thirds/v8"
out="$v8/out.gn/trech"
depot="$root/build/depot_tools"
jobs=""
debug=false
sync=true
extra=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) out="$2"; shift 2 ;;
    --depot-tools) depot="$2"; shift 2 ;;
    --jobs) jobs="$2"; shift 2 ;;
    --debug) debug=true; shift ;;
    --no-sync) sync=false; shift ;;
    --gn-args) extra="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$v8/BUILD.gn" ]]; then
  echo "thirds/v8 is not checked out; run: git submodule update --init thirds/v8" >&2
  exit 1
fi

# depot_tools provides gclient, gn and the pinned toolchain helpers.
if [[ ! -x "$depot/gclient" ]]; then
  echo "Fetching depot_tools into $depot"
  git clone --depth 1 https://chromium.googlesource.com/chromium/tools/depot_tools.git "$depot"
fi
export PATH="$depot:$PATH"
export DEPOT_TOOLS_UPDATE=0

# gclient works from the directory above the checkout. thirds/.gclient is ignored by git.
if $sync; then
  cat > "$root/thirds/.gclient" <<'EOF'
solutions = [
  {
    "name": "v8",
    "url": "https://chromium.googlesource.com/v8/v8.git",
    "deps_file": "DEPS",
    "managed": False,
    "custom_deps": {},
  },
]
EOF
  # Sync V8's dependencies for the submodule's pinned revision, without moving the checkout.
  (cd "$root/thirds" && gclient sync --no-history --shallow --nohooks \
      --revision "v8@$(git -C "$v8" rev-parse HEAD)")
  (cd "$root/thirds" && gclient runhooks)
fi

# The same ABI TRECH documents: no pointer compression and no sandbox keep the embedder's
# definitions empty; i18n is off so no ICU data file is needed at run time.
args="is_debug=$($debug && echo true || echo false)
is_component_build=false
v8_monolithic=true
v8_use_external_startup_data=false
v8_enable_i18n_support=false
v8_enable_pointer_compression=false
v8_enable_sandbox=false
treat_warnings_as_errors=false
$extra"

mkdir -p "$out"
(cd "$v8" && gn gen "$out" --args="$args")
if [[ -n "$jobs" ]]; then
  (cd "$v8" && autoninja -C "$out" -j "$jobs" v8_monolith)
else
  (cd "$v8" && autoninja -C "$out" v8_monolith)
fi

lib="$out/obj/libv8_monolith.a"
if [[ ! -f "$lib" ]]; then
  echo "build finished without $lib" >&2
  exit 1
fi
echo "Built $lib"
echo "Configure TRECH with: -DTRECH_ENABLE_V8=ON -DTRECH_V8_BUILD_DIR=$out"
