#!/usr/bin/env bash
#
# run.sh — one-shot launcher for TRECH Studio.
#
# Installs everything Studio needs (a Python venv with numpy + PySide6 + wgpu,
# plus the OS-level GUI/graphics libraries those wheels dlopen at runtime) and
# then launches the app. Idempotent: re-running only does work that is missing.
#
# Works on macOS (Homebrew) and the mainstream Linux families
# (Debian/Ubuntu · Fedora/RHEL · Arch · openSUSE · Alpine).
#
# Usage:
#   ./run.sh                       # install if needed, then launch
#   ./run.sh --open build/dev/out_viz_refraction   # args pass through to the app
#   ./run.sh --scenario experiments/foo.js
#
# Environment knobs:
#   SKIP_OS_DEPS=1   don't touch the system package manager (venv only)
#   REINSTALL=1      rebuild the venv from scratch
#   PYTHON=python3.12   pick a specific interpreter
#
set -euo pipefail

# --- locate ourselves so the script works from any CWD ----------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
OSDEPS_MARKER="$VENV_DIR/.osdeps_installed"

# --- pretty logging ---------------------------------------------------------
if [ -t 1 ]; then
  C_BLUE=$'\033[1;34m'; C_YELLOW=$'\033[1;33m'; C_RED=$'\033[1;31m'; C_RESET=$'\033[0m'
else
  C_BLUE=''; C_YELLOW=''; C_RED=''; C_RESET=''
fi
info()  { printf '%s==>%s %s\n' "$C_BLUE"   "$C_RESET" "$*"; }
warn()  { printf '%s!! %s%s\n' "$C_YELLOW" "$*" "$C_RESET" >&2; }
die()   { printf '%sxx %s%s\n' "$C_RED"    "$*" "$C_RESET" >&2; exit 1; }

have()  { command -v "$1" >/dev/null 2>&1; }

# --- privilege escalation helper -------------------------------------------
# Use sudo only when we are not already root and sudo exists.
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if have sudo; then SUDO="sudo"; fi
fi
run_root() {
  if [ -n "$SUDO" ]; then
    "$SUDO" "$@"
  elif [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    warn "need root to run: $*  (no sudo found — skipping)"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# 1. Platform + package-manager detection
# ---------------------------------------------------------------------------
OS="$(uname -s)"
PKG=""            # brew | apt | dnf | yum | pacman | zypper | apk
case "$OS" in
  Darwin) PKG="brew" ;;
  Linux)
    if   have apt-get; then PKG="apt"
    elif have dnf;     then PKG="dnf"
    elif have yum;     then PKG="yum"
    elif have pacman;  then PKG="pacman"
    elif have zypper;  then PKG="zypper"
    elif have apk;     then PKG="apk"
    else warn "no known package manager found; will assume deps are present"
    fi
    ;;
  *) warn "unsupported OS '$OS'; proceeding best-effort" ;;
esac

pkg_install() {
  # pkg_install <pkg> [<pkg> ...] — install system packages, best effort.
  [ "$#" -gt 0 ] || return 0
  case "$PKG" in
    brew)   brew install "$@" ;;
    apt)    run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@" ;;
    dnf)    run_root dnf install -y "$@" ;;
    yum)    run_root yum install -y "$@" ;;
    pacman) run_root pacman -S --needed --noconfirm "$@" ;;
    zypper) run_root zypper --non-interactive install "$@" ;;
    apk)    run_root apk add --no-cache "$@" ;;
    *)      warn "don't know how to install: $*" ;;
  esac
}

pkg_refresh() {
  # Refresh package indexes once (apt/apk need it before install).
  case "$PKG" in
    apt) run_root env DEBIAN_FRONTEND=noninteractive apt-get update -y ;;
    apk) run_root apk update ;;
    *)   : ;;
  esac
}

# ---------------------------------------------------------------------------
# 2. Ensure a usable Python (>=3.9) with venv support
# ---------------------------------------------------------------------------
PYTHON="${PYTHON:-}"
pick_python() {
  for cand in "$PYTHON" python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
    [ -n "$cand" ] || continue
    if have "$cand"; then
      # require >= 3.9
      if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)' 2>/dev/null; then
        PYTHON="$cand"
        return 0
      fi
    fi
  done
  return 1
}

if ! pick_python; then
  info "Python >=3.9 not found — installing"
  if [ "${SKIP_OS_DEPS:-0}" != "1" ]; then
    pkg_refresh
    case "$PKG" in
      brew)   pkg_install python ;;
      apt)    pkg_install python3 python3-venv python3-pip ;;
      dnf|yum) pkg_install python3 python3-pip ;;
      pacman) pkg_install python ;;
      zypper) pkg_install python3 python3-venv python3-pip ;;
      apk)    pkg_install python3 py3-pip ;;
    esac
  fi
  pick_python || die "could not find or install Python >=3.9"
fi
info "using Python: $($PYTHON --version 2>&1) ($PYTHON)"

# venv module can be a separate package on Debian derivatives.
if ! "$PYTHON" -c 'import venv' 2>/dev/null; then
  if [ "${SKIP_OS_DEPS:-0}" != "1" ]; then
    info "python venv module missing — installing"
    pkg_refresh
    case "$PKG" in
      apt)    pkg_install python3-venv ;;
      zypper) pkg_install python3-venv ;;
      *)      : ;;
    esac
  fi
  "$PYTHON" -c 'import venv' 2>/dev/null || die "python 'venv' module unavailable"
fi

# ---------------------------------------------------------------------------
# 3. OS-level runtime libraries for PySide6 (Qt/xcb) + wgpu (Vulkan)
#    macOS wheels are self-contained (Qt bundled, wgpu -> Metal). Linux needs
#    the X/Wayland client libs and a Vulkan loader + a software/HW ICD.
# ---------------------------------------------------------------------------
install_os_gui_deps() {
  [ "${SKIP_OS_DEPS:-0}" = "1" ] && { info "SKIP_OS_DEPS=1 — skipping system GUI/graphics libs"; return 0; }
  [ "$OS" = "Linux" ] || return 0        # only Linux needs these
  [ -f "$OSDEPS_MARKER" ] && [ "${REINSTALL:-0}" != "1" ] && return 0

  info "installing OS GUI/graphics libraries (PySide6 + wgpu runtime deps)"
  pkg_refresh
  case "$PKG" in
    apt)
      pkg_install \
        libgl1 libegl1 libopengl0 libglib2.0-0 libdbus-1-3 \
        libxkbcommon0 libxkbcommon-x11-0 \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
        libxcb-xkb1 libxcb-util1 libfontconfig1 \
        libvulkan1 mesa-vulkan-drivers vulkan-tools || warn "some apt packages failed"
      ;;
    dnf|yum)
      pkg_install \
        mesa-libGL mesa-libEGL glib2 dbus-libs fontconfig \
        libxkbcommon libxkbcommon-x11 \
        xcb-util-cursor xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
        vulkan-loader mesa-vulkan-drivers vulkan-tools || warn "some dnf/yum packages failed"
      ;;
    pacman)
      pkg_install \
        libglvnd glib2 dbus fontconfig \
        libxkbcommon libxkbcommon-x11 \
        xcb-util-cursor xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
        vulkan-icd-loader vulkan-mesa-layers mesa vulkan-tools || warn "some pacman packages failed"
      ;;
    zypper)
      pkg_install \
        Mesa-libGL1 Mesa-libEGL1 glib2 dbus-1 fontconfig \
        libxkbcommon0 libxkbcommon-x11-0 \
        libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
        libxcb-render-util0 libxcb-util1 \
        libvulkan1 Mesa-vulkan-device-select vulkan-tools || warn "some zypper packages failed"
      ;;
    apk)
      pkg_install \
        mesa-gl mesa-egl glib dbus-libs fontconfig \
        libxkbcommon \
        vulkan-loader mesa-vulkan-swrast || warn "some apk packages failed"
      ;;
    *)
      warn "unknown package manager — skipping OS GUI/graphics libs; the app may fail to open a window"
      ;;
  esac
  # Marker lives in the venv so REINSTALL / rm -rf .venv re-triggers it.
  mkdir -p "$VENV_DIR"
  : > "$OSDEPS_MARKER"
}

install_os_gui_deps

# ---------------------------------------------------------------------------
# 4. Virtual environment + Python dependencies (numpy, PySide6, wgpu)
# ---------------------------------------------------------------------------
if [ "${REINSTALL:-0}" = "1" ] && [ -d "$VENV_DIR" ]; then
  info "REINSTALL=1 — removing existing venv"
  rm -rf "$VENV_DIR"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  info "creating virtual environment at .venv"
  "$PYTHON" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

# Editable install: fast no-op on repeat runs, so we gate on an import probe.
if [ "${REINSTALL:-0}" = "1" ] || \
   ! "$VENV_PY" -c 'import trech_studio, numpy, PySide6, wgpu' >/dev/null 2>&1; then
  info "installing Python dependencies (numpy + PySide6 + wgpu) and trech-studio"
  "$VENV_PY" -m pip install --upgrade pip setuptools wheel
  "$VENV_PY" -m pip install -e "$SCRIPT_DIR"
else
  info "Python dependencies already present"
fi

# ---------------------------------------------------------------------------
# 5. Launch
# ---------------------------------------------------------------------------
info "launching TRECH Studio"
exec "$VENV_PY" -m trech_studio "$@"
