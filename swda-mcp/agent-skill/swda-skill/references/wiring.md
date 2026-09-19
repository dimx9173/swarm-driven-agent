# Wiring swda-mcp into prime-agent

## 1. Export env before launching prime-agent

The kernel-local MCP runtime only passes tagged env references, and only
`HOME/PATH/TMPDIR/TEMP/TMP/SystemRoot/WINDIR` are ambient. `SWDA_REPO` and
`PYTHONPATH` must exist in the launching shell:

```bash
export SWDA_REPO=/Users/carlos/pywork/swarm-driven-agent
export PYTHONPATH=/Users/carlos/pywork/swarm-driven-agent
prime-agent
```

Without these, the server fails at import and the kernel reports the server
as down (not as misconfigured).

## 2. Register the server (user scope only)

```bash
prime-agent mcp add swda \
  --cwd /Users/carlos/pywork/swarm-driven-agent/swda-mcp \
  --env SWDA_REPO=SWDA_REPO --env PYTHONPATH=PYTHONPATH \
  -- /Users/carlos/miniconda3/bin/python3 -m swda_mcp.server
```

Equivalent `~/.prime/agent/settings.json` shape:

```jsonc
{"mcpServers": {"swda": {
  "type": "stdio",
  "command": "/Users/carlos/miniconda3/bin/python3",
  "args": ["-m", "swda_mcp.server"],
  "cwd": "/Users/carlos/pywork/swarm-driven-agent/swda-mcp",
  "env": {"SWDA_REPO": {"env": "SWDA_REPO"}, "PYTHONPATH": {"env": "PYTHONPATH"}},
  "startupTimeoutMs": 20000, "callTimeoutMs": 60000
}}}
```

Project `.prime/agent/settings.json` entries are ignored for execution —
register at user scope only.

## 3. Install this skill

Copy `swda-skill/` to `~/.prime/agent/skills/swda/`
(or `.prime/agent/skills/swda/` for a project skill), then `/reload`.
The kernel installs the package editable and exposes `import swda`.

## 4. Call it

```python
import swda
v = await swda.reconcile("src/foo.py", "/path/to/repo")
assert v["verdict"] in ("valid", "unverifiable", "invalid")
# valid -> deliver; invalid -> rework; unverifiable -> human confirms
```

## Troubleshooting

- "server down" on first call: missing exported env (step 1), or the
  conda python lacks `mcp` (`/Users/carlos/miniconda3/bin/python3 -c "import mcp"`).
- `valid:true` but `verdict:"unverifiable"`: NOT clean — confirm with a human.
- `swda_stats`/`swda_models` vary by cwd: pin `cwd` in the server entry and
  always pass `workspace_root` explicitly.
