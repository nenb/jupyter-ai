"""Tests for the MCP context provider."""

import os
import pytest
import logging
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from jupyter_ai.mcp.registry import McpServerInfo
from jupyter_ai.context_providers.mcp import McpContextProvider
from jupyterlab_chat.models import Message


@pytest.fixture
def mock_mcp_registry():
    """Fixture for mocking the MCP registry."""
    with patch('jupyter_ai.context_providers.mcp.mcp_registry') as mock_registry:
        mock_registry._initialized = True
        mock_registry.get_servers.return_value = [
            McpServerInfo(
                id="test-server-123",
                name="TestServer",
                description="Test server for unit tests",
                status="available",
                capabilities={"resources": True, "tools": True, "prompts": True},
                resources=[
                    {
                        "uri": "resource://test/foo",
                        "name": "foo",
                        "description": "A test resource"
                    },
                    {
                        "uri": "resource://test/bar",
                        "name": "bar",
                        "description": "Another test resource"
                    }
                ]
            )
        ]
        mock_registry.get_server_by_name.return_value = mock_registry.get_servers.return_value[0]
        mock_registry.get_resource = AsyncMock(return_value={
            "type": "text",
            "content": "This is test resource content",
            "mime_type": "text/plain"
        })
        mock_registry._init_registry = AsyncMock(return_value=True)
        yield mock_registry


@pytest.fixture
def mcp_context_provider(mock_mcp_registry):
    """Fixture for testing the MCP context provider."""
    provider = McpContextProvider(
        log=logging.getLogger(),
        config_manager=MagicMock(),
        model_parameters={},
        root_dir="/",
        preferred_dir="/tmp",
        dask_client_future=asyncio.Future(),
        context_providers={},
    )
    provider._init_registry = AsyncMock(return_value=True)
    return provider


@pytest.mark.asyncio
async def test_mcp_context_provider_make_context(mcp_context_provider, mock_mcp_registry):
    """Test that the MCP context provider can make a context prompt."""
    # Create a test message with an MCP resource reference
    message = Message(
        id="msg123",
        body="I need information about @mcp:TestServer:foo",
        sender="user",
        timestamp=0,
    )
    
    # Call the context prompt function
    context = await mcp_context_provider.make_context_prompt(message)
    
    # Verify the result
    assert "MCP Resource from server 'TestServer': foo" in context
    assert "This is test resource content" in context
    
    # Verify the registry was called
    mcp_context_provider._init_registry.assert_called_once()
    mock_mcp_registry.get_resource.assert_called_once_with("TestServer", "foo")


@pytest.mark.asyncio
async def test_mcp_context_provider_invalid_format(mcp_context_provider):
    """Test that the MCP context provider handles invalid formats."""
    # Create a test message with an invalid MCP reference
    message = Message(
        id="msg123",
        body="I need information about @mcp:TestServer",  # Missing resource name
        sender="user",
        timestamp=0,
    )
    
    # We expect no matches for invalid format
    context = await mcp_context_provider.make_context_prompt(message)
    assert context == ""


def test_mcp_context_provider_arg_options(mcp_context_provider, mock_mcp_registry):
    """Test that the MCP context provider provides argument options."""
    # Test server list
    options = mcp_context_provider.get_arg_options("")
    assert len(options) == 1
    assert "TestServer" in options[0].label
    
    # Test resource list
    options = mcp_context_provider.get_arg_options("TestServer:")
    assert len(options) == 2
    assert any("foo" in option.label for option in options)
    assert any("bar" in option.label for option in options)