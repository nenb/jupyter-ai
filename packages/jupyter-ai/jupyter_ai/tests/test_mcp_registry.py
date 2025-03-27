"""
Tests for the MCP Registry functionality
"""

import os
import pathlib
import tempfile
import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

# Mock MCP SDK if not available
try:
    from mcp import ClientSession, StdioServerParameters
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    
    # Create mock classes for testing
    class StdioServerParameters:
        def __init__(self, command, args=None, env=None):
            self.command = command
            self.args = args or []
            self.env = env or {}
            
    class ClientSession:
        pass

from jupyter_ai.mcp.registry import McpRegistry, McpServerInfo, McpServerYamlConfig, McpYamlConfig


class TestMcpRegistry(unittest.TestCase):
    """Tests for MCP Registry functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.registry = McpRegistry()
        
        # Temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temp_dir.name)
        
    def tearDown(self):
        """Clean up after tests"""
        self.temp_dir.cleanup()
        
    def test_server_yaml_config_model(self):
        """Test YAML configuration model"""
        # Test default values
        config = McpServerYamlConfig(command="test-server")
        assert config.command == "test-server"
        assert config.args == []
        assert config.env == {}
        assert config.connection_type == "stdio"
        assert config.description is None
        assert config.endpoint is None
        
        # Test with all values
        config = McpServerYamlConfig(
            command="test-server",
            args=["--debug"],
            env={"TEST_VAR": "value"},
            description="Test server",
            connection_type="sse",
            endpoint="https://example.com/sse"
        )
        assert config.command == "test-server"
        assert config.args == ["--debug"]
        assert config.env == {"TEST_VAR": "value"}
        assert config.description == "Test server"
        assert config.connection_type == "sse"
        assert config.endpoint == "https://example.com/sse"
    
    @patch('yaml.safe_load')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_load_yaml_config(self, mock_open, mock_yaml_load):
        """Test loading YAML configuration"""
        # Create a test YAML configuration
        test_config = {
            "mcp": {
                "servers": {
                    "test-server": {
                        "command": "test-mcp-server",
                        "args": ["--debug"],
                        "env": {"TEST_VAR": "value"},
                        "description": "Test MCP Server"
                    },
                    "sse-server": {
                        "connection_type": "sse",
                        "endpoint": "https://example.com/sse",
                        "description": "SSE Server"
                    }
                }
            }
        }
        
        mock_yaml_load.return_value = test_config
        
        # Create a test config file
        config_path = self.temp_path / "jupyter_mcp_config.yaml"
        with open(config_path, 'w') as f:
            f.write("test")
            
        # Mock Path.exists to return True for our test file
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.is_file', return_value=True):
                # Mock Path paths to include our test file
                with patch.object(pathlib.Path, 'cwd', return_value=self.temp_path):
                    servers = self.registry._load_yaml_config()
                    
                    # Check results
                    assert len(servers) == 2
                    
                    # Check first server
                    assert any(s['name'] == "test-server" for s in servers)
                    test_server = next(s for s in servers if s['name'] == "test-server")
                    assert test_server['command'] == "test-mcp-server"
                    assert test_server['args'] == ["--debug"]
                    assert test_server['env'] == {"TEST_VAR": "value"}
                    assert test_server['description'] == "Test MCP Server"
                    
                    # Check second server
                    assert any(s['name'] == "sse-server" for s in servers)
                    sse_server = next(s for s in servers if s['name'] == "sse-server")
                    assert sse_server['connection_type'] == "sse"
                    assert sse_server['endpoint'] == "https://example.com/sse"
                    assert sse_server['description'] == "SSE Server"
    
    @pytest.mark.asyncio
    @patch.object(McpRegistry, '_load_yaml_config')
    @patch.object(McpRegistry, 'register_server')
    async def test_discover_servers_from_yaml(self, mock_register_server, mock_load_yaml_config):
        """Test discovering servers from YAML configuration"""
        # Mock YAML config result
        mock_load_yaml_config.return_value = [
            {
                "name": "test-server",
                "command": "test-mcp-server",
                "args": ["--debug"],
                "env": {"TEST_VAR": "value"},
                "description": "Test MCP Server",
                "connection_type": "stdio"
            },
            {
                "name": "sse-server",
                "connection_type": "sse",
                "endpoint": "https://example.com/sse",
                "description": "SSE Server"
            }
        ]
        
        # Mock register_server to return server IDs
        mock_register_server.side_effect = ["server1", "server2"]
        
        # Run discover servers
        await self.registry._discover_servers()
        
        # Check register_server was called with correct arguments
        assert mock_register_server.call_count == 2
        
        # Check first server registration
        mock_register_server.assert_any_call(
            connection_type="stdio",
            command="test-mcp-server",
            args=["--debug"],
            endpoint=None,
            env_vars={"TEST_VAR": "value"},
            name="test-server",
            description="Test MCP Server"
        )
        
        # Check second server registration
        mock_register_server.assert_any_call(
            connection_type="sse",
            command=None,
            args=[],
            endpoint="https://example.com/sse",
            env_vars={},
            name="sse-server",
            description="SSE Server"
        )
        
    @pytest.mark.asyncio
    @patch('mcp.client.stdio.stdio_client')
    async def test_register_server_with_env_vars(self, mock_stdio_client):
        """Test registering a server with environment variables"""
        if not HAS_MCP:
            pytest.skip("MCP SDK not installed")
            
        # Create mock objects for the test
        mock_transport = MagicMock()
        mock_session = AsyncMock()
        
        # Set up mock session.initialize response
        init_result = MagicMock()
        init_result.serverInfo.name = "test-server"
        init_result.instructions = "Test server instructions"
        init_result.capabilities.prompts = True
        init_result.capabilities.resources = False
        init_result.capabilities.tools = True
        
        mock_session.initialize.return_value = init_result
        
        # Set up context managers
        mock_transport_ctx = AsyncMock()
        mock_transport_ctx.__aenter__.return_value = (mock_transport,)
        mock_transport_ctx.__aexit__.return_value = None
        
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        
        mock_stdio_client.return_value = mock_transport_ctx
        mock_session.ClientSession = mock_session_ctx
        
        # Add patch for ClientSession
        with patch('jupyter_ai.mcp.registry.ClientSession', return_value=mock_session_ctx):
            # Test registering server with custom name, description, and env vars
            server_id = await self.registry.register_server(
                connection_type="stdio",
                command="test-server",
                args=["--debug"],
                env_vars={"TEST_VAR": "value"},
                name="Custom Name",
                description="Custom Description"
            )
            
            # Check server parameters
            mock_stdio_client.assert_called_once()
            args, kwargs = mock_stdio_client.call_args
            params = args[0]
            
            assert params.command == "test-server"
            assert params.args == ["--debug"]
            assert params.env == {"TEST_VAR": "value"}
            
            # Check server info was created with custom values
            server_info = self.registry._servers.get(server_id)
            assert server_info is not None
            assert server_info.name == "Custom Name"  # Should use custom name
            assert server_info.description == "Custom Description"  # Should use custom description
            assert server_info.env == {"TEST_VAR": "value"}  # Should include env vars


if __name__ == '__main__':
    unittest.main()