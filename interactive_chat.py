#!/usr/bin/env python3
"""Interactive chat with Odoo using LLM and MCP tools"""

import asyncio
import json
import os
import sys
from dotenv import load_dotenv
from odoo_mcp_client import OdooMCPClient, OdooLLMClient, OdooMCPConfig

# Load environment variables
load_dotenv()

# ANSI color codes
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header():
    print(f"\n{Colors.BOLD}{Colors.CYAN}╔════════════════════════════════════════════════════════════╗")
    print(f"║     Odoo 19 MCP - Interactive LLM Chat                   ║")
    print(f"╚════════════════════════════════════════════════════════════╝{Colors.END}")
    print(f"{Colors.YELLOW}Type 'help' for commands, 'quit' or Ctrl+C to exit{Colors.END}\n")

def print_assistant(message: str):
    print(f"{Colors.GREEN}🤖 Assistant:{Colors.END} {message}")

def print_user(message: str):
    print(f"{Colors.BLUE}👤 You:{Colors.END} {message}")

def print_system(message: str):
    print(f"{Colors.YELLOW}ℹ️  {message}{Colors.END}")

def print_error(message: str):
    print(f"{Colors.RED}✗ {message}{Colors.END}")

async def interactive_session():
    """Interactive chat session with Odoo via LLM"""
    print_header()

    # Load config
    try:
        config = OdooMCPConfig.from_env()
    except Exception as e:
        print_error(f"Configuration error: {e}")
        print_system("Please check your .env file")
        return

    # Validate LLM configuration
    if not config.llm_base_url or not config.llm_api_key:
        print_error("LLM not configured in .env")
        print_system("Required: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL")
        return

    print_system(f"Odoo URL: {config.odoo_url}")
    print_system(f"Database: {config.odoo_database}")
    print_system(f"LLM Model: {config.llm_model}")
    print_system("Initializing MCP connection...\n")

    # Create clients
    client = OdooMCPClient(config)
    llm_client = OdooLLMClient(config)

    try:
        # Start MCP client (spawns server)
        await client.start()
        print_assistant("Connected! I can now help you interact with Odoo.")
        print_system("I can search records, create entries, update data, and more.")
        print()

        # Chat history
        history = []

        while True:
            try:
                # Get user input
                user_input = input(f"{Colors.BLUE}👤 You:{Colors.END} ").strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print_system("Goodbye!")
                    break

                if user_input.lower() == 'help':
                    print(f"\n{Colors.BOLD}Available Commands:{Colors.END}")
                    print("  help    - Show this help message")
                    print("  quit    - Exit the chat")
                    print("  clear   - Clear chat history")
                    print("  status  - Show connection status")
                    print("\n" + f"{Colors.BOLD}Example queries:{Colors.END}")
                    print("  List all users in Odoo")
                    print("  Show me the sales orders from this week")
                    print("  Create a new customer named John Doe")
                    print("  Count how many products we have")
                    print("  What fields does the sale.order model have?")
                    print()
                    continue

                if user_input.lower() == 'clear':
                    history = []
                    print_system("Chat history cleared")
                    continue

                if user_input.lower() == 'status':
                    tools = await client.list_tools()
                    print(f"\n{Colors.BOLD}Connection Status:{Colors.END}")
                    print(f"  MCP Server: {Colors.GREEN}Connected{Colors.END}")
                    print(f"  Available Tools: {len(tools)}")
                    for tool in tools:
                        print(f"    - {tool.get('name')}")
                    print()
                    continue

                # Process with LLM
                print_assistant("Thinking...")
                response = await llm_client.chat(user_input, history, client)

                # Display response
                print(f"\n{Colors.GREEN}🤖 Assistant:{Colors.END} {response}\n")

                # Update history
                history.append({"role": "user", "content": user_input})
                history.append({"role": "assistant", "content": response})

            except EOFError:
                print_system("\nGoodbye!")
                break

    except KeyboardInterrupt:
        print_system("\nGoodbye!")
    except Exception as e:
        print_error(f"Error: {type(e).__name__}: {e}")
    finally:
        await client.close()

async def demo_mode():
    """Run a demo without LLM (direct MCP tool calls)"""
    print_header()
    print_system("Demo Mode: Direct MCP tool calls (no LLM required)\n")

    config = OdooMCPConfig.from_env()
    client = OdooMCPClient(config)

    try:
        await client.start()
        print_assistant("Connected to Odoo MCP Server!")

        # Helper to extract text content from MCP result
        def extract_text(mcp_result):
            """Extract text content from MCP tool result"""
            if not mcp_result:
                return None
            content = mcp_result.get('content', [])
            if content and len(content) > 0:
                return content[0].get('text', '')
            return mcp_result.get('text', '')

        # Demo: List models
        print_system("\n[Demo 1] Listing available Odoo models...")
        result = await client.call_tool("list_models", {})
        result_text = extract_text(result)
        if result_text:
            import json
            models_data = json.loads(result_text)
            model_names = models_data if isinstance(models_data, list) else models_data.get('models', [])
            print_assistant(f"Found {len(model_names)} models")
            print(f"  First 10: {', '.join(str(m) for m in model_names[:10])}")
        else:
            print_assistant("No data returned")

        # Demo: Get fields
        print_system("\n[Demo 2] Getting fields for 'res.users'...")
        fields = await client.call_tool("get_fields", {"model": "res.users"})
        fields_text = extract_text(fields)
        if fields_text:
            field_list = json.loads(fields_text)
            # get_fields returns a list of field objects
            if isinstance(field_list, list):
                print_assistant(f"Model has {len(field_list)} fields")
                field_names = [f.get('name', 'unknown') for f in field_list[:10]]
                print(f"  Key fields: {', '.join(field_names)}")
            else:
                # Handle dict format if returned
                print_assistant(f"Model has {len(field_list)} fields")
                print(f"  Key fields: {', '.join(list(field_list.keys())[:10])}")
        else:
            print_assistant("No data returned")

        # Demo: Count users
        print_system("\n[Demo 3] Counting users...")
        count = await client.call_tool("count_records", {
            "model": "res.users",
            "domain": []
        })
        count_text = extract_text(count)
        if count_text:
            import json
            count_data = json.loads(count_text)
            user_count = count_data.get('count', 0)
            print_assistant(f"Total users in database: {user_count}")
        else:
            print_assistant("No data returned")

        print(f"\n{Colors.GREEN}✓ Demo completed successfully!{Colors.END}")

    except Exception as e:
        print_error(f"Demo failed: {type(e).__name__}: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Interactive Odoo MCP Chat")
    parser.add_argument("--demo", action="store_true", help="Run demo mode (no LLM)")
    args = parser.parse_args()

    if args.demo:
        asyncio.run(demo_mode())
    else:
        asyncio.run(interactive_session())
