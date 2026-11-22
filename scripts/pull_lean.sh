#!/usr/bin/env bash
# Pull-before-use for the Lean 4 and Mathlib reference checkouts.
#
# Fast-forwards thirds/lean4 and thirds/mathlib4 to upstream master, prints the new heads,
# and checks whether thirds/lean4 sits at the Lean release Mathlib expects
# (thirds/mathlib4/lean-toolchain). Never builds anything.
# See AGENTS/engine/formal/AGENTS.md and docs/engine/formal_laws.md.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

for sub in thirds/lean4 thirds/mathlib4; do
  if [ ! -e "$sub/.git" ]; then
    echo "init $sub (shallow)"
    git submodule update --init --depth 1 "$sub"
  fi
  if [ "$(git -C "$sub" rev-parse --abbrev-ref HEAD)" != "master" ]; then
    git -C "$sub" checkout master
  fi
  echo "pull $sub"
  git -C "$sub" pull --ff-only origin master
  echo "  head: $(git -C "$sub" log -1 --format='%h %cd %s' --date=short)"
done

toolchain="$(tr -d '[:space:]' < thirds/mathlib4/lean-toolchain)"
tag="${toolchain##*:}"
echo "mathlib4 expects: $toolchain"

tag_commit="$(git -C thirds/lean4 ls-remote --tags origin "refs/tags/$tag^{}" "refs/tags/$tag" \
  | awk 'NR==1 {print $1}')"
head_commit="$(git -C thirds/lean4 rev-parse HEAD)"
if [ -z "$tag_commit" ]; then
  echo "warning: tag $tag not found on the lean4 remote" >&2
elif [ "$tag_commit" = "$head_commit" ]; then
  echo "thirds/lean4 is at $tag"
else
  echo "note: thirds/lean4 master ($(git -C thirds/lean4 rev-parse --short HEAD)) is not $tag (${tag_commit:0:10})."
  echo "      Reading sources is fine. A from-source toolchain build for Mathlib must use $tag"
  echo "      (git -C thirds/lean4 fetch --depth 1 origin tag $tag), or install it with elan."
fi

echo "Commit moved submodule pointers with the work that needed them."
