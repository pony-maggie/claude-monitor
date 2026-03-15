#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Claude Monitor — Uninstaller
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR"
PID_FILE="$INSTALL_DIR/.exporter.pid"

echo "Claude Monitor Uninstaller"
echo "=========================="
echo ""
echo "Install directory: $INSTALL_DIR"
echo ""

read -rp "Are you sure you want to uninstall? [y/N]: " CONFIRM
if [[ "${CONFIRM,,}" != "y" ]]; then
  echo "Aborted."
  exit 0
fi

# ── Stop exporter ────────────────────────────────────────────────────────
if [[ -f "$PID_FILE" ]]; then
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping exporter (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "  Exporter stopped."
fi

# ── Stop Docker stack ────────────────────────────────────────────────────
if [[ -f "$INSTALL_DIR/docker-compose.yml" ]]; then
  echo "Stopping Docker containers..."
  docker compose -f "$INSTALL_DIR/docker-compose.yml" down 2>/dev/null || true
  echo "  Containers stopped."
fi

# ── Remove symlink ───────────────────────────────────────────────────────
for bin_dir in "$HOME/.local/bin" "/usr/local/bin"; do
  if [[ -L "$bin_dir/ccmon" ]]; then
    target=$(readlink "$bin_dir/ccmon")
    if [[ "$target" == "$INSTALL_DIR/ccmon" ]]; then
      rm -f "$bin_dir/ccmon"
      echo "  Removed symlink: $bin_dir/ccmon"
    fi
  fi
done

# ── Remove install directory ─────────────────────────────────────────────
echo "Removing $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"
echo "  Directory removed."

# ── Optional: clean Docker volumes ───────────────────────────────────────
echo ""
read -rp "Also remove Docker data volumes (prometheus-data, grafana-data)? [y/N]: " CLEAN_VOLUMES
if [[ "${CLEAN_VOLUMES,,}" == "y" ]]; then
  docker volume rm claude-monitor_prometheus-data 2>/dev/null || true
  docker volume rm claude-monitor_grafana-data 2>/dev/null || true
  echo "  Volumes removed."
fi

echo ""
echo "Uninstall complete."
