# MCP servers

What the Maestro session connects to, and why. No credentials here; each server authenticates
with its own token or OAuth flow.

| Server | Transport | Used for |
|---|---|---|
| **mission-control** | stdio (`node scripts/mc-mcp-server.cjs` from the Mission Control repo) | The Maestro's main tool: create, read and update tasks, list agents and projects, read agent SOULs, cost and token stats. |
| **ERP** (3D printing business) | HTTP | Sales orders, invoices and stock for the e-commerce operation. |
| **Marketplaces and payments** | HTTP | Listings and orders on the marketplaces the 3D business sells on; payment status. |
| **Composio** | HTTP | Google Drive (product photos, spreadsheets) and Instagram through one gateway. |

## mission-control

Upstream Mission Control ships an MCP server. I extended it in my fork so the orchestrator could
route work by project:

- `mc_create_task` accepts `project_id` and `metadata` (where `dispatchCwd` lives);
- `mc_list_projects` returns `id`, `name` and `slug`, and the slug is the folder name on disk;
- a longer dispatch timeout.

Without those, the Maestro could create a task but not say which repository it belonged to,
which is the root of the "agent working in the wrong project" failure.

Registration, with placeholders:

```json
{
  "mcpServers": {
    "mission-control": {
      "command": "env",
      "args": ["MC_URL=<YOUR_MC_URL>", "MC_API_KEY=<YOUR_MC_API_KEY>",
               "node", "<path-to>/mission-control/scripts/mc-mcp-server.cjs"]
    }
  }
}
```

The server listens on localhost only. Other devices reach Mission Control over a private mesh
VPN, never the public internet.
