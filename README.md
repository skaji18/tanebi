# TANEBI — Evolving AI Agent Framework

> "Use it, and it grows smarter." / 「使えば使うほど賢くなる」

## What is TANEBI?

TANEBI (種火 — "seed fire") is an **evolving multi-agent persona framework**. In conventional multi-agent systems, agents are disposable workers: their memory resets every session, and the 100th task starts with the same capability as the first. TANEBI changes this.

At its core, TANEBI gives each agent a **Persona** — a persistent identity that grows and specializes through task execution. Success patterns are reinforced, failure patterns are recorded, and the entire team becomes compoundingly smarter over time. The Evolution Engine is the heart of the system: it drives individual agent growth and shared knowledge accumulation simultaneously.

## Quick Start

```bash
git clone https://github.com/skaji18/tanebi
cd tanebi
claude  # CLAUDE.md auto-loads — TANEBI starts as your orchestrator
```

Three steps. No tmux, no process managers, no extra infrastructure. Just Claude Code.

## Architecture

```mermaid
graph TD
    PS["Parent Session<br/>(CLAUDE.md loaded)"]
    D["Decompose<br/>Task decomposition<br/>+ Persona-based worker selection"]
    E["Execute<br/>Parallel worker launch via Task tool"]
    WA["Worker A<br/>(persona: db_specialist<br/>+ Few-Shot injected)"]
    WB["Worker B<br/>(persona: api_designer)"]
    WC["Worker C<br/>(persona: test_writer)"]
    A["Aggregate<br/>Result integration → report.md"]
    EV["Evolve<br/>Persona update + Few-Shot registration"]

    PS --> D --> E
    E --> WA & WB & WC
    WA & WB & WC --> A --> EV
```

**Five-step loop**: Orchestrate → Decompose → Execute → Aggregate → Evolve. Each cycle makes the team stronger.

## Persona — The Agent's Identity

Every agent carries a **4-layer Persona** defined in YAML:

```mermaid
graph TD
    L4["Layer 4: Identity<br/>Name, speech style, archetype, base model<br/>— Most stable (changes monthly)"]
    L3["Layer 3: Knowledge<br/>Domain proficiency, Few-Shot examples, anti-patterns<br/>— Grows with every task"]
    L2["Layer 2: Behavior<br/>Risk tolerance, detail orientation, speed vs quality<br/>— Evolves over multiple tasks"]
    L1["Layer 1: Performance<br/>Trust score, success rate, quality average, streaks<br/>— Measured objectively per task"]

    L4 --> L3 --> L2 --> L1

    style L4 fill:#4a90d9,color:#fff
    style L3 fill:#7ab648,color:#fff
    style L2 fill:#f5a623,color:#fff
    style L1 fill:#d0021b,color:#fff
```

Personas persist across sessions. Copy them, merge them, version them — they are the living memory of your agent team.

## Evolution Engine

TANEBI runs a **dual evolution** architecture:

- **Individual Evolution** — Each agent's Persona evolves through selection, mutation, crossover, and fitness evaluation. Success reinforces traits; failure triggers correction.
- **Knowledge Evolution** — A shared **Few-Shot Bank** accumulates successful task examples. New workers automatically receive relevant examples from past successes. A knowledge GC prevents bloat.

The **fitness score** drives decisions:

```
fitness = 0.35 × quality + 0.30 × completion_rate + 0.20 × efficiency + 0.15 × growth_rate
```

Agents that perform well get more tasks in their domain. Agents that struggle get corrective feedback baked into their Persona. The team self-optimizes.

## Commands

| Command | Description |
|---------|-------------|
| `bash scripts/new_cmd.sh "<task>"` | Create new task workspace |
| `bash scripts/show_evolution.sh` | Show all Persona KPIs |
| `bash scripts/evolve.sh <cmd_id>` | Run evolution after task completion |
| `bash scripts/persona_ops.sh list` | List all Personas |
| `bash scripts/persona_ops.sh copy <src> <new>` | Copy a Persona |

## Project Structure

```
tanebi/
  CLAUDE.md              # Orchestrator instructions (auto-loaded)
  config.yaml            # Framework configuration
  personas/
    active/              # Currently active Personas
    library/             # Templates & snapshots
    history/             # Version history
  knowledge/
    few_shot_bank/       # Success example library
    episodes/            # Episode memory
  work/                  # Task workspaces (cmd_001/, cmd_002/, ...)
  templates/             # Worker / Decomposer / Aggregator templates
  scripts/               # Evolution & Persona operation scripts
  modules/               # Pluggable modules (Trust, Cognitive, etc.)
  docs/                  # Design documents
```

## Documentation

- [Design Document](docs/design.md) — Full architecture, Persona spec, Evolution Engine, MVP roadmap

## License

MIT
