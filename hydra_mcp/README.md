# Hydra MCP Server

Exposes Hydra read-only operations as MCP tools so **Claude Cowork / Code**
agents (using your existing subscription) can query and reason about your
phone farm without any extra API cost.

## Available tools (phase 1 — read-only)

| Tool | What it does |
|------|--------------|
| `hydra_list_devices` | All devices + engine running status (optionally filter) |
| `hydra_running_engines` | Snapshot of run_device.py PIDs alive right now |
| `hydra_query_accounts` | Filter accounts by tag / status / device / username |
| `hydra_get_account_detail` | Full info for one account + recent login attempts |
| `hydra_get_device_log` | Tail N lines of a device's bot-engine log (with grep) |
| `hydra_analyze_recent_failures` | Bucket recent login failures by reason |
| `hydra_predict_account_risk` | Risk score per account (jagger-pattern detection) |
| `hydra_get_mother_stats` | Mother + slave performance summary |

All tools are **read-only and safe**. Write tools (schedule / restart / grant)
will be added in phase 2 after we confirm the chat experience works.

## Install in Claude Code (Windows)

Add to your Claude Code MCP config. Two common locations:

### Option A — project-local (recommended)
Create `.claude/mcp_servers.json` in any project where you want Hydra access:

```json
{
  "mcpServers": {
    "hydra": {
      "command": "C:\\Users\\TheLiveHouse\\clawd\\phone-farm\\venv\\Scripts\\python.exe",
      "args": ["-m", "hydra_mcp"],
      "cwd": "C:\\Users\\TheLiveHouse\\clawd\\phone-farm"
    }
  }
}
```

### Option B — global user config
`%USERPROFILE%\.claude.json` or use the Claude Code CLI:

```cmd
claude mcp add hydra -- C:\Users\TheLiveHouse\clawd\phone-farm\venv\Scripts\python.exe -m hydra_mcp
```

The `cwd` setting (working directory) is important — server resolves DB and
log paths relative to the phone-farm root.

## Install in Claude Desktop (Windows)

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hydra": {
      "command": "C:\\Users\\TheLiveHouse\\clawd\\phone-farm\\venv\\Scripts\\python.exe",
      "args": ["-m", "hydra_mcp"]
    }
  }
}
```

Restart Claude Desktop. Tools appear under the 🔌 connector menu.

## Example conversations

After install, ask Claude things like:

> "Which Hydra accounts have the highest ban risk right now?"
> → calls `hydra_predict_account_risk(min_score=60)` and explains the patterns.

> "Show me what CRAIG 1 was doing in the last hour."
> → calls `hydra_get_device_log(device_serial="192.168.132.89_5555", tail_lines=200)`.

> "Summarise the last 48 hours of login attempts and tell me which devices
> had the worst success rate."
> → uses `hydra_analyze_recent_failures(hours=48)`.

> "How are the chantall slaves doing? Any of them dormant?"
> → uses `hydra_get_mother_stats("chantall.main")` (or `query_accounts`).

## Routines

Set up a recurring routine in Claude Cowork (or use `/loop` skill in Code):

> Every night at 04:00:
> 1. Call `hydra_predict_account_risk(min_score=70)`.
> 2. If any account has score ≥ 80, append a row to a Google Sheet / email me.
> 3. List devices whose engine isn't running via `hydra_list_devices(only_running=False)`.

## Run standalone for debugging

```cmd
C:\Users\TheLiveHouse\clawd\phone-farm\venv\Scripts\python.exe -m hydra_mcp
```

It will read MCP protocol messages from stdin — quit with Ctrl+C. To exercise
tools directly without MCP framing, import and call:

```python
from hydra_mcp.server import hydra_predict_account_risk
print(hydra_predict_account_risk(min_score=60))
```
