"""
MCP Chat Handler for Jupyter-AI

This module provides a chat handler for MCP slash commands.
"""

import logging
import shlex
import json
import re


from jupyter_ai.chat_handlers.base import BaseChatHandler, SlashCommandRoutingType
from jupyterlab_chat.models import Message
from .registry import mcp_registry

logger = logging.getLogger("jupyter_ai.mcp.chat_handler")

class McpChatHandler(BaseChatHandler):
    """Handler for MCP commands in the chat interface"""

    id = "mcp"
    name = "MCP"
    help = "Interact with MCP servers to get context"
    routing_type = SlashCommandRoutingType(slash_id="mcp")
    uses_llm = False  # This handler doesn't use the LLM directly

    async def process_message(self, human_message: Message):
        """Process an MCP command message"""
        # Parse the command
        try:
            tokens = shlex.split(human_message.body)
        except ValueError as e:
            # Handle quoting errors
            self.reply(f"Error parsing command: {str(e)}", human_message)
            return

        if len(tokens) < 2:
            # Not enough arguments
            self.reply("Usage: /mcp <server_name> [command] [arguments]", human_message)
            return

        # Extract components
        server_name = tokens[1]
        
        # Get available servers to display in case of error
        servers = []
        if mcp_registry._initialized:
            servers = [s.name for s in mcp_registry.get_servers()]
        
        # If no servers available, display useful message
        if not servers:
            self.reply("No MCP servers available. Please configure MCP servers and try again.", human_message)
            return
            
        # Check if the specified server exists
        server = mcp_registry.get_server_by_name(server_name)
        if not server:
            servers_list = ", ".join(servers) if servers else "None"
            self.reply(f"Error: MCP server '{server_name}' not found.\n\nAvailable servers: {servers_list}", human_message)
            return
            
        # Parse command and arguments
        command = ""
        args = {}
        
        if len(tokens) > 2:
            command = tokens[2]
            
            # Process any additional arguments if provided
            if len(tokens) > 3:
                arg_tokens = tokens[3:]
                
                # Check if we have key=value format or positional arguments
                has_key_value_pattern = any('=' in arg for arg in arg_tokens)
                
                if has_key_value_pattern:
                    # Process as key=value pairs
                    for arg in arg_tokens:
                        # Match key=value pattern
                        match = re.match(r'^([^=]+)=(.*)$', arg)
                        if match:
                            key, value = match.groups()
                            # Try to parse as JSON for numbers, booleans, etc.
                            try:
                                value = json.loads(value)
                            except (json.JSONDecodeError, ValueError):
                                # If not valid JSON, keep as string
                                pass
                            args[key] = value
                else:
                    # Process as positional arguments
                    # For the greeting command, use "name" parameter
                    args["input"] = " ".join(arg_tokens)
        
        logger.debug(f"MCP command: server={server_name}, command={command}, args={args}")

        # Execute the command with arguments
        result = await mcp_registry.execute_command(
            server_name=server_name,
            command=command,
            arguments=args
        )

        # Add result to context for the LLM
        context = []
        if result["type"] == "text":
            context.append({
                "type": "mcp_result",
                "server": server_name,
                "command": command,
                "content": result["content"]
            })

        # Create a message with the result
        message_text = result["content"]
        
        # Currently BaseChatHandler.reply() doesn't support metadata,
        # so we'll just send the message without it for now
        # TODO: Add metadata support to BaseChatHandler.reply() or
        # create a custom reply implementation
        
        # Reply with the result
        self.reply(message_text, human_message)

        # Return context for LLM
        return {"context": context}

    async def handle_exc(self, e: Exception, human_message: Message):
        """Handle exceptions from MCP command execution"""
        logger.error(f"Error handling MCP command: {e}")
        self.reply(f"Error executing MCP command: {str(e)}", human_message)
