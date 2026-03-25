"""
Odoo MCP Client

This client connects to the odoo_mcp_server.py using stdio transport,
providing an interface for interacting with Odoo 19 through MCP protocol.

Environment Variables:
    ODOO_URL: Odoo server URL (default: http://localhost:8069)
    ODOO_DATABASE: Database name (default: odoo19)
    ODOO_API_KEY: API key for authentication
    READONLY_MODE: Set to "true" to disable write operations (default: false)
    LLM_BASE_URL: LLM API base URL (for OpenAI-compatible API)
    LLM_API_KEY: LLM API key
    LLM_MODEL: LLM model name (default: qwen3.5-plus)
    MCP_SERVER_PATH: Path to odoo_mcp_server.py (default: ./odoo_mcp_server.py)
    MCP_TIMEOUT: Timeout for MCP operations in seconds (default: 30)
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)


# =============================================================================
# Exception Classes
# =============================================================================

class OdooMCPError(Exception):
    """Base exception for Odoo MCP client errors."""
    pass


class OdooMCPConnectionError(OdooMCPError):
    """Exception raised when connection to MCP server fails."""
    pass


class OdooMCPTimeoutError(OdooMCPError):
    """Exception raised when MCP operation times out."""
    pass


class OdooMCPToolError(OdooMCPError):
    """Exception raised when MCP tool execution fails."""
    pass


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class OdooMCPConfig:
    """Configuration for Odoo MCP client."""
    odoo_url: str
    odoo_database: str
    odoo_api_key: str
    readonly_mode: bool = False
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: str = "qwen3.5-plus"
    mcp_server_path: str = "./odoo_mcp_server.py"
    mcp_timeout: int = 30

    @classmethod
    def from_env(cls) -> "OdooMCPConfig":
        """Create configuration from environment variables."""
        return cls(
            odoo_url=os.getenv("ODOO_URL", "http://localhost:8069"),
            odoo_database=os.getenv("ODOO_DATABASE", "odoo19"),
            odoo_api_key=os.getenv("ODOO_API_KEY", ""),
            readonly_mode=os.getenv("READONLY_MODE", "false").lower() == "true",
            llm_base_url=os.getenv("LLM_BASE_URL"),
            llm_api_key=os.getenv("LLM_API_KEY"),
            llm_model=os.getenv("LLM_MODEL", "qwen3.5-plus"),
            mcp_server_path=os.getenv("MCP_SERVER_PATH", "./odoo_mcp_server.py"),
            mcp_timeout=int(os.getenv("MCP_TIMEOUT", "30")),
        )

    def validate(self) -> None:
        """Validate required configuration fields."""
        if not self.odoo_url:
            raise ValueError("ODOO_URL is required")
        if not self.odoo_database:
            raise ValueError("ODOO_DATABASE is required")
        if not self.odoo_api_key:
            raise ValueError("ODOO_API_KEY is required")
        if not self.mcp_server_path:
            raise ValueError("MCP_SERVER_PATH is required")


# =============================================================================
# Odoo MCP Client (Core MCP Protocol)
# =============================================================================

class OdooMCPClient:
    """MCP client for connecting to odoo_mcp_server.py using stdio transport."""

    def __init__(self, config: OdooMCPConfig):
        """Initialize the Odoo MCP client.

        Args:
            config: OdooMCPConfig instance with connection settings
        """
        self.config = config
        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._initialized = False
        self._protocol_version = "2024-11-05"

    def _next_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def start(self) -> dict:
        """Start the MCP server process and initialize the session.

        Returns:
            Server initialization response

        Raises:
            OdooMCPConnectionError: If connection to server fails
        """
        logger.info(f"Starting MCP server: {self.config.mcp_server_path}")

        try:
            # Start the MCP server subprocess
            self.process = await asyncio.create_subprocess_exec(
                "python",
                self.config.mcp_server_path,
                "--transport",
                "stdio",
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Suppress stderr
                cwd=os.path.dirname(os.path.abspath(self.config.mcp_server_path))
            )

            # Wait a moment for the server to start
            await asyncio.sleep(0.5)

            # Initialize the session
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {
                        "roots": {"listChanged": True},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "odoo-mcp-client",
                        "version": "1.0.0"
                    }
                }
            }

            await self._send_request(init_request)
            response = await self._read_response()

            if "error" in response:
                raise OdooMCPConnectionError(
                    f"Failed to initialize MCP server: {response['error']}"
                )

            self._initialized = True
            logger.info("MCP server initialized successfully")
            return response.get("result", {})

        except (ConnectionError, OSError, BrokenPipeError) as e:
            logger.exception(f"Connection error during MCP server start")
            if self.process:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    if self.process.returncode is None:
                        self.process.kill()
                        await self.process.wait()
                self.process = None
            raise OdooMCPConnectionError(f"Failed to start MCP server: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error during MCP server start")
            if self.process:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    if self.process.returncode is None:
                        self.process.kill()
                        await self.process.wait()
                self.process = None
            raise OdooMCPConnectionError(f"Failed to start MCP server: {str(e)}")

    async def _send_request(self, request: dict) -> None:
        """Send a JSON-RPC request to the server.

        Args:
            request: JSON-RPC request dictionary

        Raises:
            OdooMCPConnectionError: If server is not running or send fails
        """
        if not self.process or not self.process.stdin:
            raise OdooMCPConnectionError("MCP server process not running")

        try:
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str.encode())
            await self.process.stdin.drain()
        except (ConnectionError, OSError, BrokenPipeError) as e:
            logger.exception(f"Connection error sending request to MCP server")
            raise OdooMCPConnectionError(f"Failed to send request: {str(e)}")

    async def _read_response(self, timeout: Optional[float] = None) -> dict:
        """Read a JSON-RPC response from the server.

        Args:
            timeout: Optional timeout in seconds (defaults to config.mcp_timeout)

        Returns:
            JSON-RPC response dictionary

        Raises:
            OdooMCPTimeoutError: If read times out
            OdooMCPConnectionError: If server is not running or read fails
        """
        if not self.process or not self.process.stdout:
            raise OdooMCPConnectionError("MCP server process not running")

        timeout = timeout or self.config.mcp_timeout

        try:
            # Read data in chunks to handle very large responses
            # (workaround for StreamReader size limits)
            buffer = bytearray()
            chunk_size = 64 * 1024  # 64KB chunks

            while b'\n' not in buffer:
                chunk = await asyncio.wait_for(
                    self.process.stdout.read(chunk_size),
                    timeout=timeout
                )
                if not chunk:
                    if not buffer:
                        raise OdooMCPConnectionError("No response from MCP server")
                    break
                buffer.extend(chunk)

            # Split at first newline and decode
            line_bytes = buffer.split(b'\n', 1)[0]
            if not line_bytes:
                raise OdooMCPConnectionError("Empty response from MCP server")

            return json.loads(line_bytes.decode().strip())

        except asyncio.TimeoutError:
            logger.warning(f"MCP server response timeout after {timeout} seconds")
            raise OdooMCPTimeoutError(
                f"MCP server response timeout after {timeout} seconds"
            )
        except json.JSONDecodeError as e:
            logger.exception(f"Invalid JSON response from MCP server")
            raise OdooMCPConnectionError(f"Invalid JSON response: {str(e)}")

    async def list_tools(self) -> list[dict]:
        """List available tools from the MCP server.

        Returns:
            List of tool dictionaries with name, description, and inputSchema

        Raises:
            OdooMCPToolError: If tool list retrieval fails
        """
        if not self._initialized:
            await self.start()

        await self._send_request({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        })

        response = await self._read_response()

        if "error" in response:
            raise OdooMCPToolError(f"Failed to list tools: {response['error']}")

        return response.get("result", {}).get("tools", [])

    def _normalize_arguments(self, tool_name: str, arguments: dict) -> dict:
        """Normalize tool arguments to handle LLM quirks.

        Some LLMs (like qwen) serialize list/dict parameters as JSON strings.
        This function detects and parses such parameters.

        Args:
            tool_name: Name of the tool being called
            arguments: Raw arguments from LLM

        Returns:
            Normalized arguments with proper types
        """
        normalized = {}
        # Parameters that should be lists/dicts, not strings
        list_params = {'domain', 'fields', 'args', 'ids', 'attributes', 'field_filter'}
        dict_params = {'kwargs', 'values', 'context'}

        for key, value in arguments.items():
            if key in list_params and isinstance(value, str):
                try:
                    normalized[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    normalized[key] = value
            elif key in dict_params and isinstance(value, str):
                try:
                    normalized[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    normalized[key] = value
            else:
                normalized[key] = value

        return normalized

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Call an MCP tool by name.

        Args:
            name: Tool name (e.g., 'list_models', 'search_records')
            arguments: Tool arguments dictionary

        Returns:
            Tool result (varies by tool)

        Raises:
            OdooMCPToolError: If tool execution fails
            ValueError: If tool name or arguments are invalid
        """
        # Validate tool name
        if not name or not isinstance(name, str):
            raise ValueError("Tool name must be a non-empty string")

        # Validate arguments
        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a dictionary")

        # Normalize arguments (fix stringified JSON from some LLMs)
        arguments = self._normalize_arguments(name, arguments)

        logger.debug(f"Calling tool: {name} with arguments: {arguments}")

        if not self._initialized:
            await self.start()

        await self._send_request({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        })

        response = await self._read_response()

        if "error" in response:
            logger.error(f"Tool '{name}' failed: {response['error']}")
            raise OdooMCPToolError(
                f"Tool '{name}' failed: {response['error']}"
            )

        return response.get("result")

    async def list_resources(self) -> list[dict]:
        """List available resources from the MCP server.

        Returns:
            List of resource dictionaries with URI and description

        Raises:
            OdooMCPError: If resource list retrieval fails
        """
        if not self._initialized:
            await self.start()

        await self._send_request({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "resources/list",
            "params": {}
        })

        response = await self._read_response()

        if "error" in response:
            raise OdooMCPError(f"Failed to list resources: {response['error']}")

        return response.get("result", {}).get("resources", [])

    async def read_resource(self, uri: str) -> str:
        """Read an MCP resource by URI.

        Args:
            uri: Resource URI (e.g., 'odoo://models', 'odoo://model/res.partner')

        Returns:
            Resource content as string

        Raises:
            OdooMCPError: If resource read fails
        """
        if not self._initialized:
            await self.start()

        await self._send_request({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "resources/read",
            "params": {
                "uri": uri
            }
        })

        response = await self._read_response()

        if "error" in response:
            raise OdooMCPError(f"Failed to read resource '{uri}': {response['error']}")

        # Handle both direct text content and wrapped content
        result = response.get("result", {})

        # If result has contents array
        if "contents" in result:
            contents = result["contents"]
            if contents and isinstance(contents[0], dict):
                # Check for text content
                if contents[0].get("type") == "text":
                    return contents[0].get("text", "")
                # Check for text field directly
                elif "text" in contents[0]:
                    return contents[0]["text"]

        # If result is a dict with text field
        if isinstance(result, dict) and "text" in result:
            return result["text"]

        # Fallback: return string representation
        return str(result)

    async def close(self) -> None:
        """Close the MCP server process and cleanup resources."""
        if self.process:
            try:
                if self.process.returncode is None:  # Only terminate if still running
                    self.process.terminate()
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        if self.process.returncode is None:
                            self.process.kill()
                            await self.process.wait()
            except Exception as e:
                # Log but don't raise - cleanup should always succeed
                logger.warning(f"Error during MCP server cleanup: {e}")
            finally:
                self.process = None
                self._initialized = False
                logger.info("MCP server connection closed")


# =============================================================================
# Odoo LLM Client (LLM Integration)
# =============================================================================

class OdooLLMClient:
    """LLM client with Odoo-specific system prompt and tool calling."""

    # Available Odoo MCP tools for reference
    AVAILABLE_TOOLS = [
        "list_models - List all available Odoo models",
        "get_fields - Get field information for a specific model",
        "search_records - Search for records in an Odoo model",
        "count_records - Count records matching criteria",
        "read_records - Read specific records by IDs",
        "create_record - Create new record(s)",
        "update_record - Update existing records",
        "delete_record - Delete records",
        "execute_method - Execute any method on an Odoo model"
    ]

    def __init__(self, config: OdooMCPConfig):
        """Initialize the Odoo LLM client.

        Args:
            config: OdooMCPConfig instance with LLM settings
        """
        if not config.llm_base_url or not config.llm_api_key:
            raise ValueError("LLM_BASE_URL and LLM_API_KEY are required for LLM client")

        self.client = OpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key
        )
        self.model = config.llm_model
        self.config = config
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build Odoo-specific system prompt."""
        readonly_warning = (
            "\n\n⚠️ **READONLY MODE IS ENABLED** ⚠️\n"
            "Write operations (create, update, delete) are BLOCKED. "
            "You can only use read-only operations: list_models, get_fields, "
            "search_records, count_records, read_records."
            if self.config.readonly_mode else ""
        )

        return f"""You are an expert Odoo assistant with access to an Odoo 19 database.

CRITICAL: After getting tool results, provide a final answer to the user. STOP making tool calls once you have the data needed.

Available tools:
- list_models: List all available Odoo models
- get_fields: Get field information for a model
- search_records: Search and retrieve records (use domain filters)
- count_records: Count matching records
- read_records: Read specific records by IDs
- create_record: Create new records
- update_record: Update existing records
- delete_record: Delete records
- execute_method: Execute any Odoo model method

Common models: res.partner (contacts/customers), sale.order (sales), product.product (products), res.users (users), account.move (invoices)

IMPORTANT QUERY PATTERNS (follow these exactly):
1. "Find records in a country": Use `[["country_id.name", "ilike", "Country Name"]]`
2. "Contacts of Company X": First `search_records` for company name, then `search_records` with `[["parent_id", "=", company_id]]`
3. "Show all X": Use `search_records` with appropriate domain and limit=100
4. "Count X": Use `count_records` with domain

Domain syntax:
- `[["field", "=", "value"]]` - Equality
- `[["field", "ilike", "value"]]` - Case-insensitive search
- `[["parent_id", "=", ID]]` - Find child contacts of a company{readonly_warning}

Response format: Provide clear summaries with counts and key details."""

    def convert_mcp_tool_to_openai(self, mcp_tool: dict) -> dict:
        """Convert MCP tool schema to OpenAI function call format.

        Args:
            mcp_tool: MCP tool dictionary with name, description, inputSchema

        Returns:
            OpenAI function format dictionary
        """
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.get("name"),
                "description": mcp_tool.get("description", ""),
                "parameters": mcp_tool.get("inputSchema", {})
            }
        }

    async def chat(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        mcp_client: Optional[OdooMCPClient] = None
    ) -> str:
        """Send chat message with tool calling support.

        Args:
            message: User message
            history: Optional conversation history (list of {role, content} dicts)
            mcp_client: Optional OdooMCPClient for tool execution

        Returns:
            Assistant response text
        """
        if not mcp_client:
            raise ValueError("mcp_client is required for tool calling")

        # Build messages
        messages = [
            {"role": "system", "content": self._system_prompt}
        ]

        # Add history
        if history:
            messages.extend(history)

        # Add user message
        messages.append({"role": "user", "content": message})

        # Get available tools
        tools = await mcp_client.list_tools()
        openai_tools = [self.convert_mcp_tool_to_openai(t) for t in tools]

        # Get LLM response
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=openai_tools
        )

        if not response or not response.choices:
            return "Sorry, I couldn't process your request."

        assistant_msg = response.choices[0].message

        # Handle tool calls
        if hasattr(assistant_msg, 'tool_calls') and assistant_msg.tool_calls:
            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": assistant_msg.tool_calls
            })

            # Execute tool calls
            for tool_call in assistant_msg.tool_calls:
                func = tool_call.function
                try:
                    result = await mcp_client.call_tool(
                        func.name,
                        json.loads(func.arguments)
                    )

                    # Extract text content from result
                    if isinstance(result, dict):
                        if 'content' in result and result['content']:
                            if isinstance(result['content'], list):
                                result_text = result['content'][0].get('text', str(result))
                            else:
                                result_text = str(result['content'])
                        elif 'structuredContent' in result:
                            result_text = json.dumps(result['structuredContent'], indent=2)
                        else:
                            result_text = json.dumps(result, indent=2, ensure_ascii=False)
                    elif isinstance(result, list):
                        result_text = json.dumps(result, indent=2, ensure_ascii=False)
                    else:
                        result_text = str(result)

                    # Add tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_text
                    })

                except Exception as e:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: {str(e)}"
                    })

            # Get final response from LLM with tool results
            # Support multi-round tool calling (LLM may make more calls after seeing results)
            max_rounds = 5  # Prevent infinite loops
            current_round = 0

            while current_round < max_rounds:
                current_round += 1
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )

                if not final_response or not final_response.choices:
                    return "Sorry, I couldn't process the tool results."

                assistant_msg = final_response.choices[0].message

                # Check if LLM wants to make more tool calls
                if hasattr(assistant_msg, 'tool_calls') and assistant_msg.tool_calls:
                    # Add assistant message
                    messages.append({
                        "role": "assistant",
                        "content": assistant_msg.content or "",
                        "tool_calls": assistant_msg.tool_calls
                    })

                    # Execute new tool calls
                    for tool_call in assistant_msg.tool_calls:
                        func = tool_call.function
                        try:
                            result = await mcp_client.call_tool(
                                func.name,
                                json.loads(func.arguments)
                            )

                            # Extract text content from result
                            if isinstance(result, dict):
                                if 'content' in result and result['content']:
                                    if isinstance(result['content'], list):
                                        result_text = result['content'][0].get('text', str(result))
                                    else:
                                        result_text = str(result['content'])
                                elif 'structuredContent' in result:
                                    result_text = json.dumps(result['structuredContent'], indent=2)
                                else:
                                    result_text = json.dumps(result, indent=2, ensure_ascii=False)
                            elif isinstance(result, list):
                                result_text = json.dumps(result, indent=2, ensure_ascii=False)
                            else:
                                result_text = str(result)

                            # Add tool result message
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result_text
                            })

                        except Exception as e:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": f"Error: {str(e)}"
                            })
                    # Continue loop to process new tool results
                else:
                    # No more tool calls, return the final text response
                    return assistant_msg.content or ""

            return "Maximum tool calling rounds reached. Please try a more specific query."

        # No tool calls, return direct response
        return assistant_msg.content or ""


# =============================================================================
# Convenience Functions
# =============================================================================

async def create_odoo_mcp_client(
    config: Optional[OdooMCPConfig] = None
) -> OdooMCPClient:
    """Create and initialize an Odoo MCP client.

    Args:
        config: Optional OdooMCPConfig (uses env vars if not provided)

    Returns:
        Initialized OdooMCPClient instance

    Raises:
        OdooMCPConnectionError: If connection fails
    """
    if config is None:
        config = OdooMCPConfig.from_env()

    config.validate()

    client = OdooMCPClient(config)
    await client.start()
    return client


def create_odoo_llm_client(
    config: Optional[OdooMCPConfig] = None
) -> OdooLLMClient:
    """Create an Odoo LLM client.

    Args:
        config: Optional OdooMCPConfig (uses env vars if not provided)

    Returns:
        OdooLLMClient instance

    Raises:
        ValueError: If LLM configuration is missing
    """
    if config is None:
        config = OdooMCPConfig.from_env()

    return OdooLLMClient(config)


# =============================================================================
# Main Entry Point (for testing)
# =============================================================================

async def main():
    """Test the Odoo MCP client."""
    print("Creating Odoo MCP client...")

    try:
        # Create config from environment
        config = OdooMCPConfig.from_env()
        config.validate()

        print(f"Config: {config}")

        # Create and start MCP client
        mcp_client = OdooMCPClient(config)
        await mcp_client.start()

        print("\n=== Available Tools ===")
        tools = await mcp_client.list_tools()
        for tool in tools:
            print(f"- {tool['name']}: {tool.get('description', 'No description')}")

        print("\n=== Available Resources ===")
        resources = await mcp_client.list_resources()
        for resource in resources:
            print(f"- {resource['uri']}: {resource.get('name', 'No name')}")

        # Test list_models tool
        print("\n=== Testing list_models ===")
        result = await mcp_client.call_tool("list_models", {"name_filter": "res"})
        print(result)

        # Close client
        await mcp_client.close()
        print("\n[OK] Test completed successfully!")

    except Exception as e:
        print(f"\n[ERROR] Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
