# Odoo 19 MCP Client - Gradio Web Interface

## Quick Start

### 1. Install Dependencies
```bash
conda activate odoo19-mcp-client
pip install -r requirements.txt
```

### 2. Configure Environment (.env file)
```env
# Odoo Configuration
ODOO_URL=http://localhost:8069
ODOO_DATABASE=odoo19
ODOO_API_KEY=your_api_key_here

# LLM Configuration (for Chat tab)
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=qwen3.5-122b-a10b

# MCP Configuration
READONLY_MODE=false
MCP_SERVER_PATH=./odoo_mcp_server.py
MCP_TIMEOUT=30
```

### 3. Run the App
```bash
python odoo_gradio_app.py
```

### 4. Open in Browser
Navigate to: **http://localhost:7860**

---

## Tabs Overview

### 🔍 Search Tab
- Browse and search Odoo records
- Use domain filters (Odoo syntax)
- Example: `[["is_company", "=", true], ["country_id.name", "ilike", "USA"]]`

### 💬 Chat Tab
- Natural language queries
- Context-aware (remembers previous messages)
- Example: "How many customers do we have in USA?"

### ⚙️ Tools Tab
- Direct access to all 9 MCP tools
- JSON input/output
- For advanced users and debugging

### 📝 Create Tab
- Create, update, or delete records
- JSON data format
- Load fields button shows available fields

---

## MCP Tools Available

| Tool | Description |
|------|-------------|
| `list_models` | List all Odoo models |
| `get_fields` | Get field information for a model |
| `search_records` | Search records with domain filters |
| `count_records` | Count matching records |
| `read_records` | Read records by IDs |
| `create_record` | Create new record(s) |
| `update_record` | Update existing records |
| `delete_record` | Delete records |
| `execute_method` | Execute model methods |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Gradio Web UI                            │
│                                                               │
│   [🔍 Search]  [💬 Chat]  [⚙️ Tools]  [📝 Create]          │
│                                                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              odoo_gradio_app.py                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Singleton MCP Client (shared across all tabs/users) │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ stdio (MCP protocol)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              odoo_mcp_server.py                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MCP Server with 9 tools (FastMCP)                   │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ JSON-RPC/2
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Odoo 19 Instance                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### "LLM client not configured"
The Chat tab requires LLM credentials. Check your `.env` file:
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

### "Failed to initialize MCP clients"
Check Odoo configuration:
- Odoo is running at `ODOO_URL`
- Database name is correct (`ODOO_DATABASE`)
- API key is valid (`ODOO_API_KEY`)

### Port 7860 already in use
Change the port in `odoo_gradio_app.py`:
```python
app.launch(server_port=7861)  # Use different port
```

---

## Features

- ✅ **Singleton MCP Client** - Shared connection for all users
- ✅ **Session-based Memory** - Chat history per session
- ✅ **All 4 Tabs** - Search, Chat, Tools, Create
- ✅ **Async Design** - Proper async/await patterns
- ✅ **Error Handling** - User-friendly error messages
- ✅ **Auto Cleanup** - Proper resource cleanup on shutdown

---

## Next Steps

For production deployment:
1. Add authentication (user login)
2. Use SQLite/Redis for persistent chat memory
3. Add rate limiting
4. Deploy with Docker
5. Use HTTPS
