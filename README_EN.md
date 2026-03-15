# Claude Monitor

[中文](README.md)

> One command to track every dollar and every token spent in Claude Code.

Claude Monitor is a lightweight, real-time monitoring tool for Claude Code. It parses local JSONL logs and builds a Prometheus + Grafana dashboard to track token usage, API costs, tool invocations, context window size, and more.

![Cost & Tokens](img/1.png)

![Tools & Context](img/2.png)

![Details](img/3.png)

## Features

- **Cost Tracking** — Real-time USD cost breakdown by model (Opus / Sonnet / Haiku), including cache read/write details
- **Token Analytics** — Full-dimension stats: input / output / cache_read / cache_write
- **Tool Usage Monitoring** — Top 10 tools, call rate trends over time
- **Performance Metrics** — Average/P95 turn duration, API error rate, context compaction events
- **Multi-Project Support** — Filter by project to view all Claude Code workspaces at a glance
- **One-Command Setup** — `ccmon` spins up Prometheus + Grafana + Exporter automatically

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Claude Code (generates JSONL logs under `~/.claude/projects/`)

## Installation

```bash
# Download the release archive
tar xzf claude-monitor-1.0.0.tar.gz
cd claude-monitor-1.0.0

# One-line install
./install.sh
```

The installer copies files to `~/.claude-monitor`, sets up a Python virtual environment, and creates the `ccmon` command in `~/.local/bin`.

## Usage

```bash
# Start monitoring
ccmon

# Start monitoring and launch Claude Code
ccmon -c

# Stop all services
ccmon stop
```

Grafana dashboard opens automatically at `http://localhost:3000` after startup.

## Architecture

```
~/.claude/projects/**/*.jsonl
        │
        ▼
  claude_exporter.py (:9091/metrics)
        │
        ▼
    Prometheus (:9090)
        │
        ▼
    Grafana (:3000)
```

