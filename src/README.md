# Completed Lab Implementation

This `src/` folder contains a runnable offline implementation of the memory-system lab.

- `BaselineAgent` keeps only per-thread short-term memory.
- `AdvancedAgent` combines per-thread memory, persistent `User.md`, and compact memory.
- The benchmark includes the standard suite and long-context stress suite.
- Provider config supports: `openai`, `custom`, `gemini`, `anthropic`, `ollama`, `openrouter`.

Useful commands:

```bash
python -m pytest -q src
python src/benchmark.py
```

Datasets are available at the repo root in `data/`.
