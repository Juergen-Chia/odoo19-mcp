# Odoo 19 MCP Server & Client

A full-stack **Model Context Protocol (MCP)** integration for Odoo 19, enabling AI-powered natural language interaction with any Odoo model through a Gradio web interface. Talk to your ERP — no Odoo expertise required.

---

## Architecture

```
Gradio Web UI (odoo_gradio_app.py)
        │
        ▼
Odoo MCP Client (odoo_mcp_client.py)   ◄──── LLM (Qwen / OpenAI-compatible)
        │  stdio / JSON-RPC
        ▼
Odoo MCP Server (odoo_mcp_server.py)
        │  odoolib JSON-RPC
        ▼
    Odoo 19 Instance
```

| Layer | File | Role |
|---|---|---|
| **Web UI** | `odoo_gradio_app.py` | Gradio app — Chat, Search, Tools, CRUD tabs |
| **MCP Client** | `odoo_mcp_client.py` | Async client + LLM tool-calling bridge |
| **MCP Server** | `odoo_mcp_server.py` | FastMCP server exposing Odoo as MCP tools |

---

## Features

- **Natural language chat** — Ask questions like *"Show me all unpaid invoices from last month"* and the LLM maps your query to the right Odoo operations automatically
- **Multi-round tool calling** — LLM can chain up to 5 sequential MCP tool calls to answer complex queries
- **Full CRUD** — Create, read, update, and delete records on any Odoo model
- **Domain-filter search** — Native Odoo search domain syntax with result pagination and sorting
- **Safe field handling** — Automatically excludes `binary`, `image`, and `html` fields to prevent oversized responses
- **Readonly mode** — Toggle `READONLY_MODE=true` to block all write operations (safe for read-only users)
- **Multi-transport** — MCP server supports `stdio`, `http`, and `sse` transports
- **Direct record URLs** — Every result includes a `_url` field for one-click browser access to the Odoo record

---

## MCP Tools Exposed

| Tool | Description |
|---|---|
| `list_models` | List all available Odoo models (with optional name filter) |
| `get_fields` | Get field definitions for a model |
| `search_records` | Search & read records with domain, offset, order |
| `count_records` | Count records matching a domain |
| `read_records` | Read specific records by ID |
| `create_record` | Create single or batch records |
| `update_record` | Update records by ID |
| `delete_record` | Delete records by ID |
| `execute_method` | Call any arbitrary method on an Odoo model |

---

## Prerequisites

- Python 3.11+
- Odoo 19 instance (local or remote)
- Odoo API key (`Settings > Technical > API Keys`)
- An OpenAI-compatible LLM API key (e.g. Qwen/DashScope, OpenAI) — required for the Chat tab

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Juergen-Chia/Odoo-18-MCP-Server.git
cd Odoo-18-MCP-Server

# Install dependencies
pip install gradio pandas python-dotenv openai odoolib fastmcp
```

---

## Configuration

Create a `.env` file in the project root:

```env
# Odoo Connection (required)
ODOO_URL=http://localhost:8069
ODOO_DATABASE=odoo19
ODOO_API_KEY=your_odoo_api_key_here

# Safety
READONLY_MODE=false          # Set to true to disable all write operations

# LLM (required for Chat tab)
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=qwen-plus          # Any OpenAI-compatible model name

# MCP Server Path
MCP_SERVER_PATH=./odoo_mcp_server.py
MCP_TIMEOUT=30
```

---

## Usage

### Option 1 — Gradio Web Interface (recommended)

```bash
python odoo_gradio_app.py
```

Open your browser at **http://localhost:7860**

The app has four tabs:

- **💬 Chat** — Converse with your Odoo data in plain language. The LLM automatically selects and chains the right MCP tools.
- **🔍 Search** — Search any model with Odoo domain filter syntax and view results as a table.
- **⚙️ Tools** — Run any MCP tool directly with raw JSON parameters.
- **📝 Create** — Create, update, or delete records with a guided form.

### Option 2 — MCP Server only (CLI / Claude Desktop / other MCP clients)

```bash
# stdio transport (default — for Claude Desktop / subprocess usage)
python odoo_mcp_server.py --transport stdio

# HTTP transport
python odoo_mcp_server.py --transport http --host 0.0.0.0 --port 8000

# SSE transport
python odoo_mcp_server.py --transport sse --host 0.0.0.0 --port 8000
```

### Option 3 — MCP Client only (programmatic)

```python
import asyncio
from odoo_mcp_client import OdooMCPClient, OdooMCPConfig

async def main():
    config = OdooMCPConfig.from_env()
    client = OdooMCPClient(config)
    await client.start()

    result = await client.call_tool("search_records", {
        "model": "res.partner",
        "domain": [["is_company", "=", True]],
        "limit": 10
    })
    print(result)
    await client.close()

asyncio.run(main())
```

---

## Domain Filter Examples

```json
// All active companies
[["is_company", "=", true], ["active", "=", true]]

// Partners in Singapore or Malaysia
["|", ["country_id.name", "=", "Singapore"], ["country_id.name", "=", "Malaysia"]]

// Odoo 19+ nested any operator
[["order_line", "any", [["product_uom_qty", ">", 5]]]]

// Records created in the last 7 days
[["create_date", ">=", "2026-03-18 00:00:00"]]
```

---

## Project Structure

```
.
├── odoo_mcp_server.py     # FastMCP server — Odoo tools via JSON-RPC
├── odoo_mcp_client.py     # Async MCP client + LLM tool-calling bridge
├── odoo_gradio_app.py     # Gradio web interface
├── .env                   # Environment variables (not committed)
└── README.md
```

---

## Acknowledgements

Server design inspired by [twtrubiks/odoo19-mcp-server](https://github.com/twtrubiks/odoo19-mcp-server).  
Built with [FastMCP](https://github.com/jlowin/fastmcp), [odoolib](https://github.com/OCA/odoorpc), [Gradio](https://gradio.app), and [OpenAI Python SDK](https://github.com/openai/openai-python).

---

## License

MIT
