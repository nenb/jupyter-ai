from typing import TYPE_CHECKING, Dict, List, Optional, Type, cast
import json
import logging

# Set up logger
logger = logging.getLogger("jupyter_ai")

# Check for MCP support
try:
    import mcp
    HAS_MCP = True
    logger.info(f"MCP SDK found.")
except ImportError:
    HAS_MCP = False
    logger.warning("MCP SDK not found. MCP functionality will be disabled.")

from jupyter_ai.chat_handlers import (
    AskChatHandler,
    DefaultChatHandler,
    GenerateChatHandler,
    HelpChatHandler,
    LearnChatHandler,
    SlashCommandRoutingType,
)

if HAS_MCP:
    try:
        from jupyter_ai.mcp.chat_handler import McpChatHandler, McpServerChatHandler
        from jupyter_ai.mcp.registry import mcp_registry
        logger.info("MCP chat handlers and registry imported successfully")
    except ImportError as e:
        # If we encounter an error importing our MCP modules despite the SDK being present,
        # log the error but allow the extension to continue
        logger.error(f"Error importing MCP modules: {e}")
        HAS_MCP = False
from jupyter_ai.config_manager import ConfigManager, KeyEmptyError, WriteConflictError
from jupyter_ai.context_providers import BaseCommandContextProvider, ContextCommand
from jupyter_server.base.handlers import APIHandler as BaseAPIHandler
from pydantic import ValidationError
from tornado import web
from tornado.web import HTTPError

from .models import (
    ListOptionsEntry,
    ListOptionsResponse,
    ListProvidersEntry,
    ListProvidersResponse,
    ListSlashCommandsEntry,
    ListSlashCommandsResponse,
    UpdateConfigRequest,
)

from tornado.web import url as url_path_join

if TYPE_CHECKING:
    from jupyter_ai_magics.embedding_providers import BaseEmbeddingsProvider
    from jupyter_ai_magics.providers import BaseProvider

    from .chat_handlers import BaseChatHandler
    from .context_providers import BaseCommandContextProvider

# TODO v3: unify loading of chat handlers in a single place, then read
# from that instead of this hard-coded dict.
CHAT_HANDLER_DICT = {
    "default": DefaultChatHandler,
    "/ask": AskChatHandler,
    "/learn": LearnChatHandler,
    "/generate": GenerateChatHandler,
    "/help": HelpChatHandler,
}

# Add MCP handlers if available
if HAS_MCP:
    try:
        from jupyter_ai.mcp.chat_handler import McpChatHandler
        CHAT_HANDLER_DICT["/mcp"] = McpChatHandler
        logger.info("Added MCP chat handler to handler dictionary")
    except ImportError as e:
        logger.error(f"Failed to import McpChatHandler: {e}")
        # Don't set HAS_MCP to False here as we still want to try to load other MCP features


class ProviderHandler(BaseAPIHandler):
    """
    Helper base class used for HTTP handlers hosting endpoints relating to
    providers. Wrapper around BaseAPIHandler.
    """

    @property
    def lm_providers(self) -> Dict[str, "BaseProvider"]:
        return self.settings["lm_providers"]

    @property
    def em_providers(self) -> Dict[str, "BaseEmbeddingsProvider"]:
        return self.settings["em_providers"]

    @property
    def allowed_models(self) -> Optional[List[str]]:
        return self.settings["allowed_models"]

    @property
    def blocked_models(self) -> Optional[List[str]]:
        return self.settings["blocked_models"]

    def _filter_blocked_models(self, providers: List[ListProvidersEntry]):
        """
        Satisfy the model-level allow/blocklist by filtering models accordingly.
        The provider-level allow/blocklist is already handled in
        `AiExtension.initialize_settings()`.
        """
        if self.blocked_models is None and self.allowed_models is None:
            return providers

        def filter_predicate(local_model_id: str):
            model_id = provider.id + ":" + local_model_id
            if self.blocked_models:
                return model_id not in self.blocked_models
            else:
                return model_id in cast(List, self.allowed_models)

        # filter out every model w/ model ID according to allow/blocklist
        for provider in providers:
            provider.models = list(filter(filter_predicate, provider.models or []))
            provider.chat_models = list(
                filter(filter_predicate, provider.chat_models or [])
            )
            provider.completion_models = list(
                filter(filter_predicate, provider.completion_models or [])
            )

        # filter out every provider with no models which satisfy the allow/blocklist, then return
        return filter((lambda p: len(p.models) > 0), providers)


class ModelProviderHandler(ProviderHandler):
    @web.authenticated
    def get(self):
        providers = []

        # Step 1: gather providers
        for provider in self.lm_providers.values():
            optionals = {}
            if provider.model_id_label:
                optionals["model_id_label"] = provider.model_id_label

            providers.append(
                ListProvidersEntry(
                    id=provider.id,
                    name=provider.name,
                    models=provider.models,
                    chat_models=provider.chat_models(),
                    completion_models=provider.completion_models(),
                    help=provider.help,
                    auth_strategy=provider.auth_strategy,
                    registry=provider.registry,
                    fields=provider.fields,
                    **optionals,
                )
            )

        # Step 2: sort & filter providers
        providers = self._filter_blocked_models(providers)
        providers = sorted(providers, key=lambda p: p.name)

        # Finally, yield response.
        response = ListProvidersResponse(providers=providers)
        self.finish(response.model_dump_json())


class EmbeddingsModelProviderHandler(ProviderHandler):
    @web.authenticated
    def get(self):
        providers = []
        for provider in self.em_providers.values():
            providers.append(
                ListProvidersEntry(
                    id=provider.id,
                    name=provider.name,
                    models=provider.models,
                    help=provider.help,
                    auth_strategy=provider.auth_strategy,
                    registry=provider.registry,
                    fields=provider.fields,
                )
            )

        providers = self._filter_blocked_models(providers)
        providers = sorted(providers, key=lambda p: p.name)

        response = ListProvidersResponse(providers=providers)
        self.finish(response.model_dump_json())


class GlobalConfigHandler(BaseAPIHandler):
    """API handler for fetching and setting the
    model and emebddings config.
    """

    @property
    def config_manager(self):
        return self.settings["jai_config_manager"]

    @web.authenticated
    def get(self):
        config = self.config_manager.get_config()
        if not config:
            raise HTTPError(500, "No config found.")

        self.finish(config.model_dump_json())

    @web.authenticated
    def post(self):
        try:
            config = UpdateConfigRequest(**self.get_json_body())
            self.config_manager.update_config(config)
            self.set_status(204)
            self.finish()
        except (ValidationError, WriteConflictError, KeyEmptyError) as e:
            self.log.exception(e)
            raise HTTPError(500, str(e)) from e
        except ValueError as e:
            self.log.exception(e)
            raise HTTPError(500, str(e.cause) if hasattr(e, "cause") else str(e))
        except Exception as e:
            self.log.exception(e)
            raise HTTPError(
                500, "Unexpected error occurred while updating the config."
            ) from e


class ApiKeysHandler(BaseAPIHandler):
    @property
    def config_manager(self) -> ConfigManager:  # type:ignore[override]
        return self.settings["jai_config_manager"]

    @web.authenticated
    def delete(self, api_key_name: str):
        try:
            self.config_manager.delete_api_key(api_key_name)
        except Exception as e:
            raise HTTPError(500, str(e))


# MCP Handlers
if HAS_MCP:
    class McpServersHandler(BaseAPIHandler):
        """Handler for MCP server information"""
        
        @web.authenticated
        async def get(self):
            """Get all registered MCP servers"""
            # Initialize registry if needed
            if not mcp_registry._initialized:
                await mcp_registry.initialize()
            
            servers = mcp_registry.get_servers()
            self.write(json.dumps([server.dict() for server in servers]))


    class McpCommandsHandler(BaseAPIHandler):
        """Handler for available MCP commands"""
        
        @web.authenticated
        async def get(self):
            """Get all available MCP commands"""
            # Initialize registry if needed
            if not mcp_registry._initialized:
                await mcp_registry.initialize()
            
            servers = mcp_registry.get_servers()
            commands = []
            
            for server in servers:
                commands.append({
                    "serverName": server.name,
                    "commandName": server.name,  # Use server name as command for MVP
                    "description": server.description,
                    "serverStatus": server.status
                })
                
                # Also include specific commands from the server
                if server.capabilities.get("prompts"):
                    for prompt in server.prompts:
                        commands.append({
                            "serverName": server.name,
                            "commandName": prompt["name"],
                            "description": prompt["description"] or f"Prompt from {server.name}",
                            "serverStatus": server.status,
                            "type": "prompt"
                        })
                
                if server.capabilities.get("tools"):
                    for tool in server.tools:
                        commands.append({
                            "serverName": server.name,
                            "commandName": tool["name"],
                            "description": tool["description"] or f"Tool from {server.name}",
                            "serverStatus": server.status,
                            "type": "tool"
                        })
            
            self.write(json.dumps(commands))
            
            
    class McpCommandArgumentsHandler(BaseAPIHandler):
        """Handler for MCP command argument suggestions"""
        
        @web.authenticated
        async def get(self):
            """Get argument suggestions for MCP commands"""
            # Initialize registry if needed
            if not mcp_registry._initialized:
                await mcp_registry.initialize()
            
            command = self.get_query_argument("command", None)
            if not command:
                self.write(json.dumps([]))
                return
                
            # Parse command to extract server and subcommand
            parts = command.split(' ', 1)
            server_name = parts[0]
            if server_name.startswith('/'):
                server_name = server_name[1:]
                
            subcommand = parts[1] if len(parts) > 1 else ""
            
            # Get server and argument options
            server = mcp_registry.get_server_by_name(server_name)
            if not server:
                self.write(json.dumps([]))
                return
                
            # Find matching prompt or tool
            options = []
            
            # If we have a subcommand, look for its parameters
            if subcommand:
                if server.capabilities.get("prompts"):
                    for prompt in server.prompts:
                        if prompt["name"] == subcommand:
                            for arg in prompt.get("arguments", []):
                                options.append({
                                    "id": arg["name"],
                                    "description": arg["description"] or f"Argument for {subcommand}",
                                    "required": arg.get("required", False)
                                })
                            break
                                
                if server.capabilities.get("tools") and not options:
                    for tool in server.tools:
                        if tool["name"] == subcommand:
                            schema = tool.get("inputSchema", {})
                            if schema and isinstance(schema, dict):
                                for prop_name, prop in schema.get("properties", {}).items():
                                    options.append({
                                        "id": prop_name,
                                        "description": prop.get("description", f"Parameter for {subcommand}"),
                                        "required": prop_name in schema.get("required", [])
                                    })
                            break
            # If no subcommand, suggest available tools and prompts
            else:
                if server.capabilities.get("prompts"):
                    for prompt in server.prompts:
                        options.append({
                            "id": prompt["name"],
                            "description": prompt["description"] or f"Prompt from {server.name}",
                            "type": "prompt"
                        })
                
                if server.capabilities.get("tools"):
                    for tool in server.tools:
                        options.append({
                            "id": tool["name"],
                            "description": tool["description"] or f"Tool from {server.name}",
                            "type": "tool"
                        })
            
            self.write(json.dumps(options))


    class McpExecuteHandler(BaseAPIHandler):
        """Handler for executing MCP commands"""
        
        @web.authenticated
        async def post(self):
            """Execute an MCP command"""
            # Initialize registry if needed
            if not mcp_registry._initialized:
                await mcp_registry.initialize()
            
            data = self.get_json_body()
            server_name = data.get("serverName", "")
            command = data.get("command", "")
            
            # Execute with appropriate arguments based on presence of command
            if command:
                result = await mcp_registry.execute_command(
                    server_name=server_name,
                    command=command
                )
            else:
                result = await mcp_registry.execute_command(
                    server_name=server_name
                )
            self.write(json.dumps(result))


class SlashCommandsInfoHandler(BaseAPIHandler):
    """List slash commands that are currently available to the user."""

    @property
    def config_manager(self) -> ConfigManager:  # type:ignore[override]
        return self.settings["jai_config_manager"]

    @property
    def chat_handlers(self) -> Dict[str, Type["BaseChatHandler"]]:
        return CHAT_HANDLER_DICT

    @web.authenticated
    def get(self):
        response = ListSlashCommandsResponse()

        # if no selected LLM, return an empty response
        if not self.config_manager.lm_provider:
            self.finish(response.model_dump_json())
            return

        for id, chat_handler in self.chat_handlers.items():
            # filter out any chat handler that is not a slash command
            if (
                id == "default"
                or chat_handler.routing_type.routing_method != "slash_command"
            ):
                continue

            # hint the type of this attribute
            routing_type: SlashCommandRoutingType = chat_handler.routing_type

            # filter out any chat handler that is unsupported by the current LLM
            if (
                "/" + routing_type.slash_id
                in self.config_manager.lm_provider.unsupported_slash_commands
            ):
                continue

            response.slash_commands.append(
                ListSlashCommandsEntry(
                    slash_id=routing_type.slash_id, description=chat_handler.help
                )
            )

        # sort slash commands by slash id and deliver the response
        response.slash_commands.sort(key=lambda sc: sc.slash_id)
        self.finish(response.model_dump_json())


class AutocompleteOptionsHandler(BaseAPIHandler):
    """List context that are currently available to the user."""

    @property
    def config_manager(self) -> ConfigManager:  # type:ignore[override]
        return self.settings["jai_config_manager"]

    @property
    def context_providers(self) -> Dict[str, "BaseCommandContextProvider"]:
        return self.settings["jai_context_providers"]

    @property
    def chat_handlers(self) -> Dict[str, Type["BaseChatHandler"]]:
        return CHAT_HANDLER_DICT

    @web.authenticated
    def get(self):
        response = ListOptionsResponse()

        # if no selected LLM, return an empty response
        if not self.config_manager.lm_provider:
            self.finish(response.model_dump_json())
            return

        partial_cmd = self.get_query_argument("partialCommand", None)
        if partial_cmd:
            # if providing options for partial command argument
            cmd = ContextCommand(cmd=partial_cmd)
            context_provider = next(
                (
                    cp
                    for cp in self.context_providers.values()
                    if isinstance(cp, BaseCommandContextProvider)
                    and cp.command_id == cmd.id
                ),
                None,
            )
            if (
                cmd.arg is not None
                and context_provider
                and isinstance(context_provider, BaseCommandContextProvider)
            ):
                response.options = context_provider.get_arg_options(cmd.arg)
        else:
            response.options = (
                self._get_slash_command_options() + self._get_context_provider_options()
            )
        self.finish(response.model_dump_json())

    def _get_slash_command_options(self) -> List[ListOptionsEntry]:
        options = []
        for id, chat_handler in self.chat_handlers.items():
            # filter out any chat handler that is not a slash command
            if id == "default" or not isinstance(
                chat_handler.routing_type, SlashCommandRoutingType
            ):
                continue

            routing_type = chat_handler.routing_type

            # filter out any chat handler that is unsupported by the current LLM
            if (
                not routing_type.slash_id
                or "/" + routing_type.slash_id
                in self.config_manager.lm_provider.unsupported_slash_commands
            ):
                continue

            options.append(
                self._make_autocomplete_option(
                    id="/" + routing_type.slash_id,
                    description=chat_handler.help,
                    only_start=True,
                    requires_arg=False,
                )
            )
        options.sort(key=lambda opt: opt.id)
        return options

    def _get_context_provider_options(self) -> List[ListOptionsEntry]:
        options = [
            self._make_autocomplete_option(
                id=context_provider.command_id,
                description=context_provider.help,
                only_start=context_provider.only_start,
                requires_arg=context_provider.requires_arg,
            )
            for context_provider in self.context_providers.values()
            if isinstance(context_provider, BaseCommandContextProvider)
        ]
        options.sort(key=lambda opt: opt.id)
        return options

    def _make_autocomplete_option(
        self,
        id: str,
        description: str,
        only_start: bool,
        requires_arg: bool,
    ):
        label = id + (":" if requires_arg else " ")
        return ListOptionsEntry(
            id=id, description=description, label=label, only_start=only_start
        )
