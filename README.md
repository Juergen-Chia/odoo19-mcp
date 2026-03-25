# Odoo 19 MCP Client Project

## Overview

A full-stack **Model Context Protocol (MCP)** integration for Odoo 19, enabling AI-powered natural language interaction with any Odoo model through a Gradio web interface. Talk to your ERP — no Odoo expertise required.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                            │
├─────────────────────────────────────────────────────────────────┤
│  odoo_gradio_app.py      - Gradio Web UI (4 tabs)               │
│  interactive_chat.py     - CLI Interactive Chat                 │
│  test_create_delete.py   - Test Suite for CRUD operations       │
├─────────────────────────────────────────────────────────────────┤
│  odoo_mcp_client.py      - MCP Client (OdooMCPClient, LLM)      │
├─────────────────────────────────────────────────────────────────┤
│  odoo_mcp_server.py      - MCP Server (9 tools, 5 resources)    │
├─────────────────────────────────────────────────────────────────┤
│                    JSON-RPC (odoolib)                           │
├─────────────────────────────────────────────────────────────────┤
│                      Odoo 19 Server                             │
└─────────────────────────────────────────────────────────────────┘
```

## Credits

### odoo_mcp_server.py

The `odoo_mcp_server.py` file is sourced from:

**https://github.com/twtrubiks/odoo19-mcp-server**

This MCP server provides 9 tools and 5 resources for interacting with Odoo 19 via JSON-RPC protocol.

### MCP Tools

| Tool | Description | ReadOnly |
|------|-------------|----------|
| `list_models` | List all available Odoo models | Yes |
| `get_fields` | Get field information for a model | Yes |
| `search_records` | Search records with domain filtering | Yes |
| `count_records` | Count records matching domain | Yes |
| `read_records` | Read records by IDs | Yes |
| `create_record` | Create new record(s) | No |
| `update_record` | Update existing records | No |
| `delete_record` | Delete records | No |
| `execute_method` | Execute any model method | Conditional |

### MCP Resources

| Resource | Description |
|----------|-------------|
| `odoo://models` | List all models |
| `odoo://model/{model_name}` | Get model fields |
| `odoo://record/{model_name}/{record_id}` | Get single record |
| `odoo://user` | Get current user info |
| `odoo://company` | Get current company info |

## Features

- **Natural language chat** — Ask questions like *"Show me all unpaid invoices from last month"* and the LLM maps your query to the right Odoo 
  operations automatically
- **Multi-round tool calling** — LLM can chain up to 5 sequential MCP tool calls to answer complex queries
- **Full CRUD** — Create, read, update, and delete records on any Odoo model
- **Domain-filter search** — Native Odoo search domain syntax with result pagination and sorting
- **Safe field handling** — Automatically excludes `binary`, `image`, and `html` fields to prevent oversized responses
- **Readonly mode** — Toggle `READONLY_MODE=true` to block all write operations (safe for read-only users)
- **Multi-transport** — MCP server supports `stdio`, `http`, and `sse` transports
- **Direct record URLs** — Every result includes a `_url` field for one-click browser access to the Odoo record

## LLM Compatibility

### Qwen Models (Alibaba DashScope)

**Status:** Compatible with known limitations

**Known Issues:**

1. **Tool Calling Limits**
   - Qwen models have a limit on the number of tools that can be passed in a single function call
   - When using all 9 MCP tools, may encounter "too many tools" errors
   - **Workaround:** Use `OdooLLMClient` with filtered tool list or process in batches

2. **Argument Normalization Required**
   - Qwen expects tool arguments in a specific format that may differ from OpenAI's schema
   - The `odoo_mcp_client.py` handles normalization for domain, fields, and other complex arguments
   - Some complex nested structures (like Odoo domains) may need additional preprocessing

3. **Token Limits**
   - Consider context window limits when returning large record sets
   - Use `limit` parameter in `search_records` to avoid truncation

**Recommended Models:**
- `qwen-plus` - Good balance of performance and cost
- `qwen-turbo` - Faster for simple queries
- `qwen-max` - Best for complex multi-step reasoning

### Alternative Models

- OpenAI `gpt-4o` / `gpt-4o-mini` - Full tool calling support
- Anthropic `claude-3-5-sonnet` - Excellent for complex tasks
- Other OpenAI-compatible APIs

## Environment Setup

```bash
# Required Environment Variables
ODOO_URL=http://localhost:8069
ODOO_DATABASE=odoo19
ODOO_API_KEY=your_api_key_here

# Optional
READONLY_MODE=false
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your_llm_api_key
LLM_MODEL=qwen3.5-122b-a10b
```

## Usage

### Gradio Web Interface

```bash
python odoo_gradio_app.py
# Access at http://localhost:7860
```

Features 4 tabs:
1. **Chat** - LLM-powered conversational interface
2. **Search** - Query Odoo with domain filters
3. **Tools** - Execute MCP tools directly
4. **Create** - Create/Update/Delete records

### CLI Interactive Chat

```bash
# With LLM
python interactive_chat.py

# Demo mode (no LLM required)
python interactive_chat.py --demo
```

### MCP Server (Direct)

```bash
# stdio transport (default)
python odoo_mcp_server.py

# HTTP transport
python odoo_mcp_server.py --transport http --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker build -t odoo-mcp-client:latest .
docker-compose up
```

## Testing

```bash
# Full test suite
python test_create_delete.py

# Dry run (preview only)
python test_create_delete.py --dry-run

# Clean up test records
python test_create_delete.py --cleanup-only
```

## Project Status

**Version:** 1.0.0
**Status:** Production Ready
**Last Updated:** 2026-03-24
**Test Coverage:** 11/11 tests passed (100%)

## License

This project incorporates code from [odoo19-mcp-server](https://github.com/twtrubiks/odoo19-mcp-server) which is subject to its own license terms.

## Support

For issues related to:
- **MCP Server:** See [odoo19-mcp-server](https://github.com/twtrubiks/odoo19-mcp-server)
- **Odoo 19 API:** [Odoo Documentation](https://odoo.com/documentation/19.0/)
