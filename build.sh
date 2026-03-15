#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Claude Monitor — Build Script
# Packages runtime files into a distributable tar.gz
# ---------------------------------------------------------------------------

VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/dist"
PKG_NAME="claude-monitor-${VERSION}"
PKG_DIR="$BUILD_DIR/$PKG_NAME"

echo "Building ${PKG_NAME}.tar.gz ..."

# ── Clean previous build ─────────────────────────────────────────────────
rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/grafana/dashboards"
mkdir -p "$PKG_DIR/grafana/provisioning/dashboards"
mkdir -p "$PKG_DIR/grafana/provisioning/datasources"

# ── Copy runtime files ───────────────────────────────────────────────────
cp "$SCRIPT_DIR/install.sh"           "$PKG_DIR/"
cp "$SCRIPT_DIR/uninstall.sh"         "$PKG_DIR/"
cp "$SCRIPT_DIR/ccmon"                "$PKG_DIR/"
cp "$SCRIPT_DIR/claude_exporter.py"   "$PKG_DIR/"
cp "$SCRIPT_DIR/requirements.txt"     "$PKG_DIR/"
cp "$SCRIPT_DIR/docker-compose.yml"   "$PKG_DIR/"
cp "$SCRIPT_DIR/prometheus.yml"       "$PKG_DIR/"

cp "$SCRIPT_DIR/grafana/dashboards/claude-monitor.json" \
   "$PKG_DIR/grafana/dashboards/"
cp "$SCRIPT_DIR/grafana/provisioning/dashboards/dashboards.yaml" \
   "$PKG_DIR/grafana/provisioning/dashboards/"
cp "$SCRIPT_DIR/grafana/provisioning/datasources/prometheus.yaml" \
   "$PKG_DIR/grafana/provisioning/datasources/"

chmod +x "$PKG_DIR/install.sh"
chmod +x "$PKG_DIR/uninstall.sh"
chmod +x "$PKG_DIR/ccmon"

# ── Create tar.gz ────────────────────────────────────────────────────────
tar -czf "$BUILD_DIR/${PKG_NAME}.tar.gz" -C "$BUILD_DIR" "$PKG_NAME"

# ── Cleanup staging dir ──────────────────────────────────────────────────
rm -rf "$PKG_DIR"

# ── Summary ──────────────────────────────────────────────────────────────
SIZE=$(du -h "$BUILD_DIR/${PKG_NAME}.tar.gz" | cut -f1)
echo ""
echo "Done: dist/${PKG_NAME}.tar.gz ($SIZE)"
echo ""
echo "Distribute this file. Users install with:"
echo "  tar xzf ${PKG_NAME}.tar.gz"
echo "  cd ${PKG_NAME}"
echo "  ./install.sh"
