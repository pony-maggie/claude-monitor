#!/usr/bin/env python3
"""Claude Code JSONL Log Exporter for Prometheus.

Parses ~/.claude/projects/**/*.jsonl to extract token usage, computes cost
from a pricing table, and exposes Prometheus metrics on :9091.
"""

import glob
import json
import os
import time

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# ---------------------------------------------------------------------------
# Pricing: $/M tokens
# ---------------------------------------------------------------------------
PRICING = {
    "opus-4.6": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_write_5m": 6.25,
        "cache_write_1h": 10.0,
    },
    "opus-4.5": {
        "input": 5.0,
        "output": 25.0,
        "cache_read": 0.50,
        "cache_write_5m": 6.25,
        "cache_write_1h": 10.0,
    },
    "sonnet-4.5": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_write_5m": 3.75,
        "cache_write_1h": 6.0,
    },
    "haiku-4.5": {
        "input": 1.0,
        "output": 5.0,
        "cache_read": 0.10,
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.0,
    },
}

DEFAULT_TIER = "sonnet-4.5"

# ---------------------------------------------------------------------------
# Model classification
# ---------------------------------------------------------------------------
_MODEL_MAP = {
    "opus-4-6": "opus-4.6",
    "opus-4-5": "opus-4.5",
    "sonnet-4-5": "sonnet-4.5",
    "haiku-4-5": "haiku-4.5",
}


def classify_model(raw_model: str) -> str:
    """Map raw model id like 'claude-opus-4-6-20250901' to pricing tier."""
    if not raw_model:
        return DEFAULT_TIER
    s = raw_model.lower()
    for pattern, tier in _MODEL_MAP.items():
        if pattern in s:
            return tier
    return DEFAULT_TIER


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
tokens_total = Counter(
    "claude_tokens_total",
    "Token consumption by type",
    ["model", "token_type", "project"],
)

cost_dollars = Counter(
    "claude_cost_dollars",
    "Cost in USD by token type",
    ["model", "token_type", "project"],
)

messages_total = Counter(
    "claude_messages_total",
    "Assistant messages count",
    ["model", "project"],
)

files_tracked = Gauge(
    "claude_files_tracked",
    "Number of JSONL files being tracked",
)

last_scan_seconds = Gauge(
    "claude_last_scan_seconds",
    "Duration of the last scan cycle in seconds",
)

tool_use_total = Counter(
    "claude_tool_use_total",
    "Tool invocations by tool name",
    ["tool", "project"],
)

turn_duration_seconds = Histogram(
    "claude_turn_duration_seconds",
    "Turn duration in seconds",
    ["project"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, float("inf")),
)

api_errors_total = Counter(
    "claude_api_errors_total",
    "API error count",
    ["project"],
)

active_sessions = Gauge(
    "claude_active_sessions",
    "Number of sessions active in the last 30 minutes",
    ["project"],
)

content_blocks_total = Counter(
    "claude_content_blocks_total",
    "Content blocks by type (thinking, text, tool_use)",
    ["block_type", "project"],
)

output_tokens_per_message = Histogram(
    "claude_output_tokens_per_message",
    "Output tokens per assistant message",
    ["model", "project"],
    buckets=(10, 50, 100, 500, 1000, 2000, 5000, 10000, float("inf")),
)

context_tokens_per_message = Histogram(
    "claude_context_tokens_per_message",
    "Total context tokens (input + cache) per assistant message",
    ["model", "project"],
    buckets=(1000, 5000, 10000, 50000, 100000, 150000, 200000, float("inf")),
)

compaction_total = Counter(
    "claude_compaction_total",
    "Conversation compaction events",
    ["project"],
)

compaction_pretokens = Histogram(
    "claude_compaction_pretokens",
    "Token count before compaction",
    ["project"],
    buckets=(10000, 50000, 100000, 150000, 200000, float("inf")),
)


# ---------------------------------------------------------------------------
# FileTracker: incremental JSONL reader
# ---------------------------------------------------------------------------
class FileTracker:
    """Track read offset for a single JSONL file."""

    def __init__(self, path: str):
        self.path = path
        self.offset = 0

    def read_new_lines(self) -> list[dict]:
        """Read new complete lines since last offset."""
        results = []
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return results
        if size <= self.offset:
            return results

        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.offset)
                data = f.read()
        except OSError:
            return results

        # Only process complete lines (ending with \n)
        if not data.endswith("\n"):
            last_nl = data.rfind("\n")
            if last_nl == -1:
                return results  # no complete line yet
            data = data[: last_nl + 1]

        self.offset += len(data.encode("utf-8"))

        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                results.append(obj)
            except json.JSONDecodeError:
                continue
        return results


# ---------------------------------------------------------------------------
# Project name extraction
# ---------------------------------------------------------------------------
_PROJECTS_PREFIX = os.path.expanduser("~/.claude/projects/")


def extract_project(filepath: str) -> str:
    """Extract project name from JSONL path.

    e.g. ~/.claude/projects/-Users-lucasma-Documents-java-projects-foo/abc.jsonl
         -> Users-lucasma-Documents-java-projects-foo
    """
    rel = filepath.replace(_PROJECTS_PREFIX, "")
    parts = rel.split("/")
    if parts:
        name = parts[0]
        # Strip leading dash
        if name.startswith("-"):
            name = name[1:]
        return name
    return "unknown"


# ---------------------------------------------------------------------------
# ClaudeExporter: main scan loop
# ---------------------------------------------------------------------------
class ClaudeExporter:
    def __init__(self, scan_interval: float = 10.0):
        self.scan_interval = scan_interval
        self.trackers: dict[str, FileTracker] = {}

    def discover_files(self) -> list[str]:
        """Find all JSONL files under ~/.claude/projects/."""
        base = os.path.expanduser("~/.claude/projects")
        pattern = os.path.join(base, "**", "*.jsonl")
        return glob.glob(pattern, recursive=True)

    def process_record(self, record: dict, project: str):
        """Process a single JSONL record.

        JSONL records are envelopes with a top-level "type" field.
        Dispatches to type-specific handlers.
        """
        rtype = record.get("type")
        if rtype == "assistant":
            self._process_assistant(record, project)
        elif rtype == "system":
            self._process_system(record, project)

    def _process_assistant(self, record: dict, project: str):
        """Process assistant records: tokens, cost, messages, tool use."""
        inner = record.get("message")
        if not inner or not isinstance(inner, dict):
            return

        # --- Content blocks: tool use + block type counting ---
        for block in inner.get("content", []):
            btype = block.get("type")
            if btype == "tool_use":
                tool_use_total.labels(
                    tool=block.get("name", "unknown"), project=project
                ).inc()
            if btype in ("thinking", "text", "tool_use"):
                content_blocks_total.labels(
                    block_type=btype, project=project
                ).inc()

        usage = inner.get("usage")
        if not usage:
            return

        model_raw = inner.get("model", "")
        model = classify_model(model_raw)

        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        cache_read = usage.get("cache_read_input_tokens", 0) or 0

        # Cache write: use the detailed breakdown if available
        cache_creation = usage.get("cache_creation", {}) or {}
        cache_write_5m = cache_creation.get("ephemeral_5m_input_tokens", 0) or 0
        cache_write_1h = cache_creation.get("ephemeral_1h_input_tokens", 0) or 0

        # Fallback: if no breakdown but total exists, count as 5m
        if cache_write_5m == 0 and cache_write_1h == 0:
            total_cache_create = usage.get("cache_creation_input_tokens", 0) or 0
            cache_write_5m = total_cache_create

        pricing = PRICING.get(model, PRICING[DEFAULT_TIER])

        token_map = {
            "input": input_tokens,
            "output": output_tokens,
            "cache_read": cache_read,
            "cache_write_5m": cache_write_5m,
            "cache_write_1h": cache_write_1h,
        }

        for token_type, count in token_map.items():
            if count > 0:
                tokens_total.labels(
                    model=model, token_type=token_type, project=project
                ).inc(count)
                cost = count * pricing[token_type] / 1_000_000
                cost_dollars.labels(
                    model=model, token_type=token_type, project=project
                ).inc(cost)

        messages_total.labels(model=model, project=project).inc()

        # --- Per-message token histograms ---
        if output_tokens > 0:
            output_tokens_per_message.labels(
                model=model, project=project
            ).observe(output_tokens)

        total_context = input_tokens + cache_read + cache_write_5m + cache_write_1h
        if total_context > 0:
            context_tokens_per_message.labels(
                model=model, project=project
            ).observe(total_context)

    def _process_system(self, record: dict, project: str):
        """Process system records: turn duration, API errors."""
        subtype = record.get("subtype")
        if subtype == "turn_duration":
            duration_ms = record.get("durationMs", 0) or 0
            if duration_ms > 0:
                turn_duration_seconds.labels(project=project).observe(
                    duration_ms / 1000.0
                )
        elif subtype == "api_error":
            api_errors_total.labels(project=project).inc()
        elif subtype == "compact_boundary":
            compaction_total.labels(project=project).inc()
            metadata = record.get("compactMetadata", {}) or {}
            pre_tokens = metadata.get("preTokens", 0) or 0
            if pre_tokens > 0:
                compaction_pretokens.labels(project=project).observe(pre_tokens)

    def scan_once(self):
        """Single scan cycle: discover files, read new lines, process."""
        t0 = time.monotonic()

        paths = self.discover_files()
        files_tracked.set(len(paths))

        now = time.time()
        active_by_project: dict[str, int] = {}

        for path in paths:
            if path not in self.trackers:
                self.trackers[path] = FileTracker(path)
            tracker = self.trackers[path]
            project = extract_project(path)

            for record in tracker.read_new_lines():
                self.process_record(record, project)

            # Active session: file modified within the last 30 minutes
            try:
                mtime = os.path.getmtime(path)
                if now - mtime < 1800:
                    active_by_project[project] = (
                        active_by_project.get(project, 0) + 1
                    )
            except OSError:
                pass

        # Reset all active_sessions labels, then set current values
        active_sessions._metrics.clear()
        for project, count in active_by_project.items():
            active_sessions.labels(project=project).set(count)

        elapsed = time.monotonic() - t0
        last_scan_seconds.set(elapsed)

    def run_forever(self):
        """Blocking loop: scan every scan_interval seconds."""
        print(f"Starting scan loop (interval={self.scan_interval}s)...")
        while True:
            try:
                self.scan_once()
            except Exception as e:
                print(f"Scan error: {e}")
            time.sleep(self.scan_interval)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    port = int(os.environ.get("EXPORTER_PORT", "9091"))
    interval = float(os.environ.get("SCAN_INTERVAL", "10"))

    print(f"Claude JSONL Exporter starting on :{port}")
    start_http_server(port)

    exporter = ClaudeExporter(scan_interval=interval)
    # Initial full scan
    exporter.scan_once()
    print(
        f"Initial scan complete: {int(files_tracked._value.get())} files tracked"
    )

    exporter.run_forever()


if __name__ == "__main__":
    main()
