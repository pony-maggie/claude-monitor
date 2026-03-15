#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Claude Monitor — Installer
# ---------------------------------------------------------------------------
VERSION="1.0.0"
DEFAULT_INSTALL_DIR="$HOME/.claude-monitor"
DEFAULT_BIN_DIR="$HOME/.local/bin"

echo "╔═══════════════════════════════════════╗"
echo "║   Claude Monitor Installer v${VERSION}    ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# ── Prerequisite checks ──────────────────────────────────────────────────
check_prereqs() {
  local missing=()
  command -v python3 >/dev/null 2>&1 || missing+=("python3")
  command -v docker  >/dev/null 2>&1 || missing+=("docker")
  if ! docker compose version >/dev/null 2>&1 && ! docker-compose version >/dev/null 2>&1; then
    missing+=("docker-compose")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Error: missing required dependencies: ${missing[*]}"
    echo "Please install them first and re-run this script."
    exit 1
  fi
}

check_prereqs

# ── Ask for install path ─────────────────────────────────────────────────
read -rp "Install directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
# Expand ~ if user typed it
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

if [[ -d "$INSTALL_DIR" ]]; then
  read -rp "Directory $INSTALL_DIR already exists. Overwrite? [y/N]: " OVERWRITE
  if [[ "${OVERWRITE,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# ── Locate source files (same dir as this script) ───────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Copy files ───────────────────────────────────────────────────────────
echo ""
echo "Installing to ${INSTALL_DIR} ..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/grafana/dashboards"
mkdir -p "$INSTALL_DIR/grafana/provisioning/dashboards"
mkdir -p "$INSTALL_DIR/grafana/provisioning/datasources"

cp "$SCRIPT_DIR/ccmon"                "$INSTALL_DIR/ccmon"
cp "$SCRIPT_DIR/claude_exporter.py"   "$INSTALL_DIR/claude_exporter.py"
cp "$SCRIPT_DIR/requirements.txt"     "$INSTALL_DIR/requirements.txt"
cp "$SCRIPT_DIR/docker-compose.yml"   "$INSTALL_DIR/docker-compose.yml"
cp "$SCRIPT_DIR/prometheus.yml"       "$INSTALL_DIR/prometheus.yml"
cp "$SCRIPT_DIR/uninstall.sh"         "$INSTALL_DIR/uninstall.sh"

cp "$SCRIPT_DIR/grafana/dashboards/claude-monitor.json" \
   "$INSTALL_DIR/grafana/dashboards/claude-monitor.json"
cp "$SCRIPT_DIR/grafana/provisioning/dashboards/dashboards.yaml" \
   "$INSTALL_DIR/grafana/provisioning/dashboards/dashboards.yaml"
cp "$SCRIPT_DIR/grafana/provisioning/datasources/prometheus.yaml" \
   "$INSTALL_DIR/grafana/provisioning/datasources/prometheus.yaml"

chmod +x "$INSTALL_DIR/ccmon"
chmod +x "$INSTALL_DIR/uninstall.sh"

echo "  Files copied."

# ── Setup Python venv ────────────────────────────────────────────────────
echo "  Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"
echo "  Python dependencies installed."

# ── Create symlink ───────────────────────────────────────────────────────
read -rp "Create 'ccmon' command in [${DEFAULT_BIN_DIR}]: " BIN_DIR
BIN_DIR="${BIN_DIR:-$DEFAULT_BIN_DIR}"
BIN_DIR="${BIN_DIR/#\~/$HOME}"

mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/ccmon" "$BIN_DIR/ccmon"
echo "  Symlink created: $BIN_DIR/ccmon -> $INSTALL_DIR/ccmon"

# ── Check PATH ───────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo ""
  echo "  ⚠  $BIN_DIR is not in your PATH."
  echo "  Add the following to your shell profile (~/.zshrc or ~/.bashrc):"
  echo ""
  echo "    export PATH=\"$BIN_DIR:\$PATH\""
  echo ""
fi

# ── Done ─────────────────────────────────────────────────────────────────
echo ""
echo "Installation complete!"
echo ""
echo "Usage:"
echo "  ccmon              Start monitoring (Prometheus + Grafana + Exporter)"
echo "  ccmon stop         Stop all services"
echo "  ccmon -c           Start monitoring and launch Claude Code"
echo ""
echo "Uninstall:"
echo "  $INSTALL_DIR/uninstall.sh"
echo ""
