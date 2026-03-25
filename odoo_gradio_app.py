"""
Odoo 19 MCP Client - Gradio Web Interface

A Gradio web application for interacting with Odoo 19 via MCP protocol.
All operations go through odoo_mcp_client.py -> odoo_mcp_server.py -> Odoo.

Architecture:
- Singleton MCP client (shared across all users/tabs)
- Session-based in-memory state (cleared on browser close)
- Async-first design with proper error handling
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
import pandas as pd
from dotenv import load_dotenv

# Import MCP client
from odoo_mcp_client import (
    OdooMCPClient,
    OdooLLMClient,
    OdooMCPConfig,
    OdooMCPToolError,
    OdooMCPError
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Global State - Singleton MCP Clients
# =============================================================================

_mcp_client: Optional[OdooMCPClient] = None
_llm_client: Optional[OdooLLMClient] = None
_clients_initialized = False


async def get_clients() -> tuple[OdooMCPClient, OdooLLMClient]:
    """Get or create global MCP clients (singleton pattern)."""
    global _mcp_client, _llm_client, _clients_initialized

    if not _clients_initialized:
        try:
            config = OdooMCPConfig.from_env()
            config.validate()

            logger.info("Initializing MCP clients...")
            _mcp_client = OdooMCPClient(config)
            await _mcp_client.start()

            if config.llm_base_url and config.llm_api_key:
                _llm_client = OdooLLMClient(config)
                logger.info("LLM client initialized")
            else:
                logger.warning("LLM credentials not configured - Chat tab will be limited")

            _clients_initialized = True
            logger.info("MCP clients initialized successfully")
        except Exception as e:
            logger.exception("Failed to initialize MCP clients")
            raise

    return _mcp_client, _llm_client


def cleanup_clients() -> None:
    """Cleanup MCP clients on shutdown."""
    global _mcp_client, _llm_client, _clients_initialized

    async def _cleanup():
        if _mcp_client:
            try:
                await _mcp_client.close()
                logger.info("MCP client closed successfully")
            except Exception as e:
                logger.warning(f"Error closing MCP client: {e}")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_cleanup())
        else:
            loop.run_until_complete(_cleanup())
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")
    finally:
        _clients_initialized = False


# Register cleanup on exit
import atexit
atexit.register(cleanup_clients)


# =============================================================================
# Session Memory (Prototype - In-Memory)
# =============================================================================

_session_memory: Dict[str, List[Dict]] = {}


def unwrap_mcp_result(result: Any) -> Any:
    """Unwrap MCP protocol response to get actual data.

    MCP returns: {'content': [{'text': '...JSON...'}], ...}
    This function extracts the actual content.
    """
    if isinstance(result, dict):
        # Check for MCP content format
        if 'content' in result:
            content = result['content']
            if isinstance(content, list) and len(content) > 0:
                first_item = content[0]
                if isinstance(first_item, dict) and 'text' in first_item:
                    # Parse JSON text content
                    text_content = first_item['text']
                    try:
                        return json.loads(text_content)
                    except:
                        return text_content
        # If not content format, return as-is
        return result
    return result


def get_session_history(session_hash: str) -> List[Dict]:
    """Get chat history for a session."""
    return _session_memory.get(session_hash, [])


def save_to_session(session_hash: str, role: str, content: str) -> None:
    """Save a message to session history."""
    if session_hash not in _session_memory:
        _session_memory[session_hash] = []
    _session_memory[session_hash].append({"role": role, "content": content})


def clear_session(session_hash: str) -> None:
    """Clear session history."""
    if session_hash in _session_memory:
        del _session_memory[session_hash]


# =============================================================================
# Tab 1: Search Records
# =============================================================================

async def search_records(
    model: str,
    domain: str,
    fields: str,
    limit: int,
    request: gr.Request
) -> tuple[pd.DataFrame, str]:
    """Search Odoo records with domain filter.

    Args:
        model: Odoo model name (e.g., res.partner)
        domain: JSON array of domain conditions
        fields: JSON array of field names to return
        limit: Maximum number of records
        request: Gradio request object

    Returns:
        Tuple of (results dataframe, status message)
    """
    try:
        client, _ = await get_clients()

        # Parse inputs
        domain_parsed = json.loads(domain) if domain else []
        fields_parsed = json.loads(fields) if fields else None

        # Call search_records tool
        result = await client.call_tool("search_records", {
            "model": model,
            "domain": domain_parsed,
            "fields": fields_parsed,
            "limit": limit
        })

        # Unwrap MCP response format
        unwrapped = unwrap_mcp_result(result)
        if isinstance(unwrapped, str):
            data = json.loads(unwrapped)
        else:
            data = unwrapped

        records = data.get("records", [])
        total = data.get("total", len(records))

        # Create dataframe
        if records:
            df = pd.DataFrame(records)
        else:
            df = pd.DataFrame()

        return df, gr.Info(f"Found {total} records")

    except json.JSONDecodeError as e:
        logger.exception("Invalid JSON in search parameters")
        return pd.DataFrame(), gr.Error(f"Invalid JSON: {str(e)}")
    except OdooMCPToolError as e:
        logger.exception("Odoo tool error")
        return pd.DataFrame(), gr.Error(f"Odoo error: {str(e)}")
    except Exception as e:
        logger.exception("Unexpected error in search")
        return pd.DataFrame(), gr.Error(f"Search failed: {str(e)}")


async def get_model_list_search() -> Dict[str, str]:
    """Get list of models for Search tab dropdown."""
    try:
        client, _ = await get_clients()
        result = await client.call_tool("list_models", {})

        # Unwrap MCP response
        models = unwrap_mcp_result(result)
        if isinstance(models, list):
            return {m: m for m in sorted(models)}
        return {}
    except Exception as e:
        logger.warning(f"Failed to load models: {e}")
        return {"res.partner": "res.partner", "res.users": "res.users"}


def build_search_tab() -> gr.Column:
    """Build the Search Records tab."""
    with gr.Column() as tab:
        gr.Markdown("## 🔍 Search Odoo Records")

        with gr.Row():
            model_input = gr.Textbox(
                label="Model",
                placeholder="e.g., res.partner",
                value="res.partner",
                info="Odoo model name"
            )
            limit_input = gr.Slider(
                label="Limit",
                minimum=1,
                maximum=1000,
                value=100,
                step=10,
                info="Maximum records to return"
            )

        domain_input = gr.Textbox(
            label="Domain (JSON)",
            placeholder='[["is_company", "=", true], ["country_id.name", "ilike", "USA"]]',
            value='[]',
            info="Odoo domain filter syntax"
        )

        fields_input = gr.Textbox(
            label="Fields (JSON, optional)",
            placeholder='["name", "email", "phone"]',
            value=None,
            info="Specific fields to return (empty = all fields)"
        )

        with gr.Row():
            search_btn = gr.Button("🔍 Search", variant="primary")
            clear_btn = gr.Button("Clear")

        results_df = gr.Dataframe(
            label="Results",
            interactive=False,
            wrap=True
        )

        status_msg = gr.Textbox(
            visible=False,
            label="Status"
        )

        # Event handlers
        search_btn.click(
            fn=search_records,
            inputs=[model_input, domain_input, fields_input, limit_input],
            outputs=[results_df, status_msg]
        )

        def clear_search():
            return pd.DataFrame(), "", "[]", None, gr.Textbox(visible=False)

        clear_btn.click(
            fn=clear_search,
            outputs=[results_df, model_input, domain_input, fields_input, status_msg]
        )

    return tab


# =============================================================================
# Tab 2: Chat with LLM
# =============================================================================

async def chat_with_llm(
    message: str,
    history: List[Dict],
    request: gr.Request
) -> tuple[List[Dict], str]:
    """Chat with Odoo using LLM.

    Args:
        message: User message
        history: Chat history from Gradio (list of dicts with role/content)
        request: Gradio request object

    Returns:
        Tuple of (updated history, tools used info)
    """
    if not message or not message.strip():
        return history, ""

    try:
        client, llm_client = await get_clients()

        if llm_client is None:
            error_msg = "LLM client not configured. Please check LLM_BASE_URL and LLM_API_KEY in .env file."
            return history + [{"role": "assistant", "content": error_msg}], ""

        # Get session history
        session_hash = request.session_hash
        stored_history = get_session_history(session_hash)

        # Use history directly (already in correct format for LLM)
        llm_history = history

        # Add current message
        llm_history = llm_history + [{"role": "user", "content": message}]

        # Call LLM with tool calling
        response = await llm_client.chat(message, history, client)

        # Save to session memory
        save_to_session(session_hash, "user", message)
        save_to_session(session_hash, "assistant", response)

        # Return new format with role/content
        return history + [{"role": "user", "content": message}, {"role": "assistant", "content": response}], ""

    except Exception as e:
        logger.exception("Chat error")
        error_msg = f"Error: {str(e)}"
        return history + [{"role": "assistant", "content": error_msg}], ""


def clear_chat(request: gr.Request) -> List[Dict]:
    """Clear chat history."""
    session_hash = request.session_hash
    clear_session(session_hash)
    return []


def build_chat_tab() -> gr.Column:
    """Build the Chat tab."""
    with gr.Column() as tab:
        gr.Markdown("## 💬 Chat with Odoo (LLM-Powered)")

        chatbot = gr.Chatbot(
            label="Conversation",
            height=700,
            elem_id="odoo-chatbot"
        )

        with gr.Row():
            msg_input = gr.Textbox(
                label="Your message",
                placeholder="Ask me anything about your Odoo data...",
                scale=4,
                autofocus=True
            )
            submit_btn = gr.Button("Send", variant="primary", scale=1)
            clear_btn = gr.Button("Clear History", scale=1)

        # Event handlers
        submit_btn.click(
            fn=chat_with_llm,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, gr.Textbox(visible=False)]
        ).then(
            lambda: "",
            outputs=[msg_input]
        )

        msg_input.submit(
            fn=chat_with_llm,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, gr.Textbox(visible=False)]
        ).then(
            lambda: "",
            outputs=[msg_input]
        )

        clear_btn.click(
            fn=clear_chat,
            outputs=[chatbot]
        )

    return tab


# =============================================================================
# Tab 3: MCP Tools (Direct Access)
# =============================================================================

# MCP tools with descriptions
MCP_TOOLS = {
    "list_models": "List all available Odoo models",
    "get_fields": "Get field information for a specific model",
    "search_records": "Search for records using domain filters",
    "count_records": "Count records matching criteria",
    "read_records": "Read specific records by IDs",
    "create_record": "Create new record(s)",
    "update_record": "Update existing records",
    "delete_record": "Delete records",
    "execute_method": "Execute any method on an Odoo model"
}


async def execute_tool(
    tool_name: str,
    arguments: str,
    request: gr.Request
) -> str:
    """Execute an MCP tool with JSON arguments.

    Args:
        tool_name: Name of the MCP tool
        arguments: JSON string of tool arguments
        request: Gradio request object

    Returns:
        JSON string of tool result
    """
    try:
        client, _ = await get_clients()

        # Parse arguments
        args_parsed = json.loads(arguments) if arguments else {}

        # Call tool
        result = await client.call_tool(tool_name, args_parsed)

        # Unwrap MCP response and format output
        unwrapped = unwrap_mcp_result(result)

        if isinstance(unwrapped, dict):
            output = json.dumps(unwrapped, indent=2, ensure_ascii=False)
        elif isinstance(result, str):
            try:
                # Try to parse and reformat for pretty print
                parsed = json.loads(result)
                output = json.dumps(parsed, indent=2, ensure_ascii=False)
            except:
                output = result
        else:
            output = json.dumps({"result": result}, indent=2, ensure_ascii=False)

        return output

    except json.JSONDecodeError as e:
        error = {"error": f"Invalid JSON in arguments: {str(e)}"}
        return json.dumps(error, indent=2)
    except OdooMCPToolError as e:
        error = {"error": f"Tool error: {str(e)}"}
        return json.dumps(error, indent=2)
    except Exception as e:
        logger.exception("Tool execution error")
        error = {"error": f"Execution failed: {str(e)}"}
        return json.dumps(error, indent=2)


def build_tools_tab() -> gr.Column:
    """Build the MCP Tools tab."""
    with gr.Column() as tab:
        gr.Markdown("## ⚙️ MCP Tools (Direct Access)")

        with gr.Row():
            tool_dropdown = gr.Dropdown(
                choices=list(MCP_TOOLS.keys()),
                value="list_models",
                label="Tool",
                info="Select MCP tool to execute"
            )

        tool_desc = gr.Markdown(
            value=f"**Description:** {MCP_TOOLS['list_models']}"
        )

        args_input = gr.Textbox(
            label="Arguments (JSON)",
            placeholder='{"model": "res.partner"}',
            value='{}',
            lines=5
        )

        with gr.Row():
            execute_btn = gr.Button("Execute Tool", variant="primary")
            clear_btn = gr.Button("Clear")

        output_box = gr.Textbox(
            label="Result",
            lines=15,
            interactive=False
        )

        # Update description when tool changes
        def update_tool_desc(tool_name: str) -> str:
            return f"**Description:** {MCP_TOOLS.get(tool_name, 'Unknown tool')}"

        tool_dropdown.change(
            fn=update_tool_desc,
            inputs=[tool_dropdown],
            outputs=[tool_desc]
        )

        # Execute tool
        execute_btn.click(
            fn=execute_tool,
            inputs=[tool_dropdown, args_input],
            outputs=[output_box]
        )

        # Clear
        def clear_tools():
            return "{}", ""

        clear_btn.click(
            fn=clear_tools,
            outputs=[args_input, output_box]
        )

    return tab


# =============================================================================
# Tab 4: Create/Update/Delete Records
# =============================================================================

async def create_update_record(
    operation: str,
    model: str,
    data: str,
    ids: str,
    request: gr.Request
) -> str:
    """Perform CRUD operations on Odoo records.

    Args:
        operation: Operation type (create/update/delete)
        model: Odoo model name
        data: JSON string of record data
        ids: Comma-separated record IDs (for update/delete)
        request: Gradio request object

    Returns:
        Success/error message
    """
    try:
        client, _ = await get_clients()

        if operation == "create":
            data_parsed = json.loads(data) if data else {}
            result = await client.call_tool("create_record", {
                "model": model,
                "data": data_parsed
            })

            # Unwrap MCP response
            unwrapped = unwrap_mcp_result(result)
            result_data = json.loads(unwrapped) if isinstance(unwrapped, str) else unwrapped
            if result_data.get("id"):
                created_ids = result_data["records"]
                return f"✅ Successfully created {len(created_ids)} record(s) with IDs: {created_ids}"
            return "✅ Record created successfully"

        elif operation == "update":
            ids_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
            data_parsed = json.loads(data) if data else {}

            result = await client.call_tool("update_record", {
                "model": model,
                "ids": ids_list,
                "values": data_parsed
            })

            return f"✅ Successfully updated {len(ids_list)} record(s): {ids_list}"

        elif operation == "delete":
            ids_list = [int(i.strip()) for i in ids.split(",") if i.strip()]

            result = await client.call_tool("delete_record", {
                "model": model,
                "ids": ids_list
            })

            return f"✅ Successfully deleted {len(ids_list)} record(s): {ids_list}"

        else:
            return "❌ Unknown operation"

    except json.JSONDecodeError as e:
        return f"❌ Invalid JSON in data: {str(e)}"
    except ValueError as e:
        return f"❌ Invalid IDs: {str(e)}"
    except OdooMCPToolError as e:
        return f"❌ Odoo error: {str(e)}"
    except Exception as e:
        logger.exception("CRUD operation error")
        return f"❌ Operation failed: {str(e)}"


async def get_model_list_crud() -> Dict[str, str]:
    """Get list of models for CRUD tab dropdown."""
    try:
        client, _ = await get_clients()
        result = await client.call_tool("list_models", {})

        # Unwrap MCP response
        models = unwrap_mcp_result(result)
        if isinstance(models, list):
            return {m: m for m in sorted(models)}
        return {}
    except Exception as e:
        logger.warning(f"Failed to load models: {e}")
        return {"res.partner": "res.partner"}


async def get_model_fields(model: str) -> str:
    """Get fields for a model as JSON example."""
    try:
        client, _ = await get_clients()
        result = await client.call_tool("get_fields", {"model": model})

        # Unwrap MCP response
        unwrapped = unwrap_mcp_result(result)
        fields = json.loads(unwrapped) if isinstance(unwrapped, str) else unwrapped

        # Build example JSON with common fields
        example = {}
        for field in fields[:10]:  # First 10 fields as example
            name = field.get("name")
            if name and not field.get("readonly") and name not in ["id", "create_date", "write_date"]:
                example[name] = f"<value for {name}>"

        return json.dumps(example, indent=2)

    except Exception as e:
        logger.warning(f"Failed to get fields: {e}")
        return '{"name": "<value>"}'


def build_create_tab() -> gr.Column:
    """Build the Create/Update/Delete tab."""
    with gr.Column() as tab:
        gr.Markdown("## 📝 Create / Update / Delete Records")

        with gr.Row():
            operation_radio = gr.Radio(
                choices=["create", "update", "delete"],
                value="create",
                label="Operation",
                info="Select CRUD operation"
            )

        model_input = gr.Textbox(
            label="Model",
            placeholder="e.g., res.partner",
            value="res.partner",
            info="Odoo model name"
        )

        load_fields_btn = gr.Button("Load Fields Example", size="sm")

        ids_input = gr.Textbox(
            label="Record IDs (for Update/Delete)",
            placeholder="e.g., 42, 43, 44",
            visible=False,
            info="Comma-separated record IDs"
        )

        data_input = gr.Textbox(
            label="Data (JSON)",
            placeholder='{"name": "New Customer", "email": "customer@example.com"}',
            value='{"name": "New Customer"}',
            lines=8
        )

        with gr.Row():
            submit_btn = gr.Button("Submit", variant="primary")
            clear_btn = gr.Button("Clear")

        result_output = gr.Textbox(
            label="Result",
            interactive=False
        )

        # Show/hide IDs field based on operation
        def toggle_ids_field(operation: str):
            return gr.Textbox(visible=(operation in ["update", "delete"]))

        operation_radio.change(
            fn=toggle_ids_field,
            inputs=[operation_radio],
            outputs=[ids_input]
        )

        # Load fields example
        load_fields_btn.click(
            fn=get_model_fields,
            inputs=[model_input],
            outputs=[data_input]
        )

        # Submit operation
        submit_btn.click(
            fn=create_update_record,
            inputs=[operation_radio, model_input, data_input, ids_input],
            outputs=[result_output]
        )

        # Clear
        def clear_create_tab():
            return '{"name": "New Customer"}', "", ""

        clear_btn.click(
            fn=clear_create_tab,
            outputs=[data_input, ids_input, result_output]
        )

    return tab


# =============================================================================
# Main Application
# =============================================================================

def build_app() -> gr.Blocks:
    """Build and return the Gradio application."""

    with gr.Blocks(title="Odoo 19 MCP Client") as app:
        # Header
        gr.Markdown(
            """
            # 📊 Odoo 19 MCP Client

            Web interface for interacting with Odoo 19 via MCP Protocol.
            """
        )

        with gr.Tabs() as tabs:
            with gr.TabItem("💬 Chat"):
                build_chat_tab()

            with gr.TabItem("🔍 Search"):
                build_search_tab()

            with gr.TabItem("⚙️ Tools"):
                build_tools_tab()

            with gr.TabItem("📝 Create"):
                build_create_tab()

        # Footer
        gr.Markdown(
            """
            ---
            **MCP Tools Available:**
            - list_models, get_fields, search_records, count_records, read_records
            - create_record, update_record, delete_record, execute_method
            """
        )

    return app


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for the Gradio app."""

    # Validate configuration
    try:
        config = OdooMCPConfig.from_env()
        config.validate()
        logger.info(f"Configuration loaded - Odoo URL: {config.odoo_url}")
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file with required variables:")
        logger.error("  - ODOO_URL")
        logger.error("  - ODOO_DATABASE")
        logger.error("  - ODOO_API_KEY")
        return

    # Build and launch app
    app = build_app()

    logger.info("Starting Gradio server...")
    logger.info("Open your browser to http://localhost:7860")

    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 1400px !important;
        }
        .chatbot {
            min-height: 400px;
        }
        /* Consistent chat font size (13px = 11px + 2px increase) */
        /* Target all chat content including tables, lists, and data */
        #odoo-chatbot,
        #odoo-chatbot *,
        #odoo-chatbot .message,
        #odoo-chatbot .message.user,
        #odoo-chatbot .message.bot,
        #odoo-chatbot .message .text,
        #odoo-chatbot .message.user .text,
        #odoo-chatbot .message.bot .text,
        #odoo-chatbot p,
        #odoo-chatbot div,
        #odoo-chatbot span,
        #odoo-chatbot table,
        #odoo-chatbot td,
        #odoo-chatbot th,
        #odoo-chatbot thead,
        #odoo-chatbot tbody,
        #odoo-chatbot tr,
        #odoo-chatbot li,
        #odoo-chatbot ul,
        #odoo-chatbot ol,
        #odoo-chatbot code,
        #odoo-chatbot pre {
            font-size: 13px !important;
            line-height: 1.4 !important;
        }
        /* Generic chatbot targeting as fallback */
        .chatbot,
        .chatbot *,
        .chatbot .message,
        .chatbot p,
        .chatbot table,
        .chatbot td,
        .chatbot th,
        .chatbot div,
        .chatbot span {
            font-size: 13px !important;
            line-height: 1.4 !important;
        }
        """
    )


if __name__ == "__main__":
    main()
