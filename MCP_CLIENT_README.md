# Odoo MCP Client Implementation

## Overview

This document describes the Odoo MCP (Model Context Protocol) client implementation for connecting to `odoo_mcp_server.py` using stdio transport.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    odoo_gradio_app.py                           │
│                    (Gradio Web UI)                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Singleton MCP Clients (shared across all users/tabs)    │  │
│  │  - OdooMCPClient: MCP protocol handling                   │  │
│  │  - OdooLLMClient: LLM integration with tool calling       │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ stdio (MCP protocol)
                             │ (JSON-RPC 2.0 message format)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    odoo_mcp_server.py                           │
│                    (FastMCP Server)                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  MCP Server - 9 tools, 4 resources                       │  │
│  │  - list_models, get_fields, search_records, etc.         │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ JSON-RPC/2
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Odoo 19 Instance                             │
│                  (localhost:8069)                               │
└─────────────────────────────────────────────────────────────────┘
```

### Protocol Layers

| Layer | Transport | Protocol |
|-------|-----------|----------|
| Gradio → MCP Client | Python (in-process) | Direct calls |
| MCP Client → MCP Server | stdio | **MCP protocol** (uses JSON-RPC 2.0 format internally) |
| MCP Server → Odoo | HTTP | **JSON-RPC/2** (Odoo's json2 API) |

## Files Created

### 1. `odoo_mcp_client.py` (Main Implementation)

**Core Components:**

#### Exception Classes
- `OdooMCPError` - Base exception for all Odoo MCP errors
- `OdooMCPConnectionError` - Connection failures
- `OdooMCPTimeoutError` - Operation timeouts
- `OdooMCPToolError` - Tool execution failures

#### Configuration
- `OdooMCPConfig` dataclass with:
  - Odoo connection settings (URL, database, API key)
  - Readonly mode flag
  - LLM configuration (base URL, API key, model)
  - MCP server settings (path, timeout)
  - `from_env()` classmethod for loading from .env
  - `validate()` method for required fields

#### OdooMCPClient Class
Core MCP protocol implementation with stdio transport:
- `start()` - Spawn subprocess and initialize MCP session
- `_send_request()` - Send MCP protocol requests (JSON-RPC 2.0 format)
- `_read_response()` - Read MCP protocol responses with timeout
- `list_tools()` - List available MCP tools
- `call_tool()` - Execute MCP tools with arguments
- `list_resources()` - List available MCP resources
- `read_resource()` - Read MCP resource contents
- `close()` - Cleanup subprocess

#### OdooLLMClient Class
LLM integration with OpenAI-compatible APIs:
- OpenAI client initialization
- `convert_mcp_tool_to_openai()` - Convert MCP tools to function format
- `chat()` - Full chat with tool calling support
- Odoo-specific system prompt with domain syntax examples

### 2. `simple_test.py` (Test Script)

Simple test demonstrating:
- Configuration loading
- Client connection
- Tool listing and execution
- Resource reading
- Proper cleanup

### 3. `example_usage.py` (Advanced Examples)

Comprehensive examples showing:
- Basic MCP client usage
- Record searching and reading
- Readonly mode for safe queries
- LLM integration (optional)

## Available Tools

The MCP server provides 9 tools:

1. **list_models** - List Odoo models
2. **get_fields** - Get field information for a model
3. **search_records** - Search records with domain
4. **count_records** - Count records matching criteria
5. **read_records** - Read specific records by IDs
6. **create_record** - Create new records
7. **update_record** - Update existing records
8. **delete_record** - Delete records
9. **execute_method** - Execute any model method

## Available Resources

The MCP server provides 3 resources:

1. **odoo://models** - List all models
2. **odoo://user** - Current user information
3. **odoo://company** - Current company information

## Configuration

Environment variables in `.env`:

```bash
# Odoo Configuration
ODOO_URL=http://localhost:8069
ODOO_DATABASE=odoo19
ODOO_API_KEY=your_api_key_here
READONLY_MODE=false

# LLM Configuration
LLM_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your_llm_api_key
LLM_MODEL=qwen3.5-plus

# MCP Server Configuration
MCP_SERVER_PATH=./odoo_mcp_server.py
MCP_TIMEOUT=30
```

## Usage Examples

### Basic Usage

```python
import asyncio
from odoo_mcp_client import OdooMCPConfig, OdooMCPClient

async def main():
    # Load configuration
    config = OdooMCPConfig.from_env()
    config.validate()

    # Create and start client
    client = OdooMCPClient(config)
    await client.start()

    try:
        # List tools
        tools = await client.list_tools()

        # Call a tool
        result = await client.call_tool("list_models", {"name_filter": "sale"})

        # Read a resource
        user_info = await client.read_resource("odoo://user")

    finally:
        await client.close()

asyncio.run(main())
```

### LLM Integration

```python
from odoo_mcp_client import OdooMCPConfig, OdooMCPClient, OdooLLMClient

async def chat_with_odoo():
    config = OdooMCPConfig.from_env()

    mcp_client = OdooMCPClient(config)
    await mcp_client.start()

    try:
        llm_client = OdooLLMClient(config)

        response = await llm_client.chat(
            message="List all sale orders",
            mcp_client=mcp_client
        )

        print(response)

    finally:
        await mcp_client.close()

asyncio.run(chat_with_odoo())
```

## Testing

Run the simple test:

```bash
python simple_test.py
```

Run the comprehensive examples:

```bash
python example_usage.py
```

## Implementation Details

### MCP Protocol Version
- Uses MCP protocol version `2024-11-05`
- Transport: stdio (MCP protocol using JSON-RPC 2.0 message format)

### Server Process Management
- Spawns `python odoo_mcp_server.py --transport stdio`
- Proper initialization with capabilities exchange
- Clean termination with timeout handling

### Error Handling
- Timeout protection for all operations
- Proper exception hierarchy
- Graceful degradation for large responses

### Thread Safety
- Each client instance manages its own subprocess
- Not thread-safe - create separate instances for concurrent use

## Dependencies

Required Python packages:
- `python-dotenv` - Environment variable loading
- `openai` - OpenAI-compatible API client
- `odoo-client-lib` - Odoo JSON-RPC/2 client library (installed in server)

## Next Steps

1. Create `requirements.txt` for deployment
2. Create Docker image for containerized deployment
3. Add more comprehensive error handling
4. Add connection pooling for multiple concurrent clients
5. Add retry logic for transient failures

## Troubleshooting

### Server Not Starting
- Verify `odoo_mcp_server.py` exists and is executable
- Check Python environment has required dependencies
- Ensure `.env` file is configured correctly

### Connection Failures
- Verify Odoo instance is running at `ODOO_URL`
- Check `ODOO_API_KEY` is valid
- Ensure `ODOO_DATABASE` exists

### Timeout Errors
- Increase `MCP_TIMEOUT` in configuration
- Check network connectivity to Odoo server
- Reduce query complexity (add limits, filters)
