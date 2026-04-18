"""
MCP Client for Playwright Communication

Manages communication between AI agents and the Playwright MCP server.
Provides tool execution, connection management, and metrics tracking.
"""

import json
import subprocess
import time
import logging
import queue
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
import threading


logger = logging.getLogger(__name__)

# MCP Protocol Version
MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class MCPToolCall:
    """Represents an MCP tool execution request"""
    tool_name: str
    arguments: Dict[str, Any]
    timestamp: datetime
    request_id: str


@dataclass
class MCPToolResponse:
    """Represents an MCP tool execution response"""
    request_id: str
    success: bool
    result: Any
    error: Optional[str]
    duration_ms: float
    timestamp: datetime


@dataclass
class ToolMetrics:
    """Metrics for a specific tool"""
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0
    latencies: List[float] = field(default_factory=list)
    
    def add_call(self, latency_ms: float, success: bool):
        """Record a tool call"""
        self.call_count += 1
        self.total_latency_ms += latency_ms
        self.latencies.append(latency_ms)
        if not success:
            self.error_count += 1
    
    def get_average_latency(self) -> float:
        """Calculate average latency"""
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count
    
    def get_percentile(self, percentile: int) -> float:
        """Calculate latency percentile (e.g., 95, 99)"""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        index = int(len(sorted_latencies) * percentile / 100)
        return sorted_latencies[min(index, len(sorted_latencies) - 1)]
    
    def get_error_rate(self) -> float:
        """Calculate error rate as percentage"""
        if self.call_count == 0:
            return 0.0
        return (self.error_count / self.call_count) * 100


class MCPClient:
    """
    Client for communicating with Playwright MCP server.
    
    Manages server lifecycle, tool execution, and metrics collection.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MCP client with configuration.
        
        Args:
            config: Configuration dictionary containing MCP settings
        """
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.connected = False
        self.available_tools: List[Dict[str, Any]] = []
        
        # Metrics tracking
        self.metrics_lock = threading.Lock()
        self.tool_metrics: Dict[str, ToolMetrics] = defaultdict(ToolMetrics)
        self.total_calls = 0
        self.total_errors = 0
        
        # Configuration
        self.timeout = config.get("timeout", 30000) / 1000  # Convert ms to seconds
        self.auto_approve = config.get("autoApprove", [])
        
        logger.info(f"MCPClient initialized with timeout={self.timeout}s")
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate MCP configuration schema.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            (is_valid, error_message) tuple
        """
        # Check if enabled field exists and is boolean
        if "enabled" in config:
            if not isinstance(config["enabled"], bool):
                return False, "mcp.enabled must be a boolean (true/false)"
        
        # If MCP is enabled, validate required fields
        if config.get("enabled", False):
            # Validate command field
            if "command" not in config:
                return False, "mcp.command is required when MCP is enabled"
            if not isinstance(config["command"], str):
                return False, "mcp.command must be a string"
            if not config["command"].strip():
                return False, "mcp.command cannot be empty"
            
            # Validate args field
            if "args" not in config:
                return False, "mcp.args is required when MCP is enabled"
            if not isinstance(config["args"], list):
                return False, "mcp.args must be a list"
            
            # Validate timeout field if present
            if "timeout" in config:
                if not isinstance(config["timeout"], (int, float)):
                    return False, "mcp.timeout must be a number"
                if config["timeout"] <= 0:
                    return False, "mcp.timeout must be a positive number"
            
            # Validate fallback_to_legacy field if present
            if "fallback_to_legacy" in config:
                if not isinstance(config["fallback_to_legacy"], bool):
                    return False, "mcp.fallback_to_legacy must be a boolean (true/false)"
            
            # Validate autoApprove field if present
            if "autoApprove" in config:
                if not isinstance(config["autoApprove"], list):
                    return False, "mcp.autoApprove must be a list"
        
        return True, None
    
    def _initialize_protocol(self) -> bool:
        """
        Perform MCP protocol initialization handshake.
        
        The MCP protocol requires a specific initialization sequence:
        1. Client sends 'initialize' request with protocol version and capabilities
        2. Server responds with its capabilities
        3. Client sends 'initialized' notification
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Step 1: Send initialize request
            initialize_request = {
                "jsonrpc": "2.0",
                "id": "initialize",
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {}  # Client supports tool execution
                    },
                    "clientInfo": {
                        "name": "ai-auto-apply-mcp-client",
                        "version": "1.0.0"
                    }
                }
            }
            
            logger.debug(f"Sending MCP initialize request with protocol version {MCP_PROTOCOL_VERSION}")
            
            # Send request
            if self.process and self.process.stdin:
                self.process.stdin.write(json.dumps(initialize_request) + "\n")
                self.process.stdin.flush()
            else:
                logger.error("MCP server process stdin not available for initialization")
                return False
            
            # Step 2: Wait for initialize response
            if self.process and self.process.stdout:
                response_line = self._read_line_with_timeout(self.process.stdout, self.timeout)
                
                if not response_line:
                    logger.error("MCP server did not respond to initialize request within timeout")
                    return False
                
                response = json.loads(response_line)
                
                # Check for error in response
                if "error" in response:
                    error_msg = response["error"].get("message", "Unknown error")
                    error_code = response["error"].get("code", "Unknown code")
                    logger.error(f"MCP initialization failed with error {error_code}: {error_msg}")
                    return False
                
                # Extract server capabilities
                result = response.get("result", {})
                server_capabilities = result.get("capabilities", {})
                server_info = result.get("serverInfo", {})
                
                logger.info(f"MCP server initialized: {server_info.get('name', 'unknown')} v{server_info.get('version', 'unknown')}")
                logger.debug(f"Server capabilities: {server_capabilities}")
            else:
                logger.error("MCP server process stdout not available for initialization")
                return False
            
            # Step 3: Send initialized notification
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            
            logger.debug("Sending MCP initialized notification")
            
            if self.process and self.process.stdin:
                self.process.stdin.write(json.dumps(initialized_notification) + "\n")
                self.process.stdin.flush()
            else:
                logger.error("MCP server process stdin not available for initialized notification")
                return False
            
            logger.info("MCP protocol initialization completed successfully")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse MCP server response during initialization: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"MCP protocol initialization failed: {e}", exc_info=True)
            return False
    
    def connect(self) -> bool:
        """
        Establish connection to MCP server by spawning the Playwright MCP server process.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self.connected:
            logger.warning("MCP client already connected")
            return True
        
        try:
            # Get command and args from config
            command = self.config.get("command", "npx")
            args = self.config.get("args", ["-y", "@playwright/mcp-server"])
            
            # Build full command
            full_command = [command] + args
            
            logger.info(f"Starting MCP server: {' '.join(full_command)}")
            
            # Spawn MCP server process with stdio communication
            self.process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=(sys.platform == "win32")
            )
            
            # Wait a moment for server to initialize
            time.sleep(2)
            
            # Check if process is still running
            if self.process.poll() is not None:
                stderr_output = self.process.stderr.read() if self.process.stderr else ""
                logger.error(f"MCP server process terminated immediately. stderr: {stderr_output}")
                return False
            
            # Perform MCP protocol initialization handshake
            logger.info("Performing MCP protocol initialization handshake")
            if not self._initialize_protocol():
                logger.error("MCP protocol initialization failed")
                # Clean up the process
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except Exception as cleanup_error:
                    logger.warning(f"Error during process cleanup: {cleanup_error}")
                    try:
                        self.process.kill()
                        self.process.wait()
                    except:
                        pass
                return False
            
            self.connected = True
            logger.info("MCP server connection established")
            
            # Discover available tools
            tools = self.list_tools()
            
            # Validate critical tools are available
            if not self._validate_critical_tools(tools):
                logger.error("Critical MCP tools missing, connection failed")
                self.disconnect()
                return False
            
            return True
            
        except FileNotFoundError as e:
            logger.error(f"MCP server command not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}", exc_info=True)
            return False
    
    def disconnect(self):
        """
        Cleanly shutdown MCP server connection.
        """
        if not self.connected:
            logger.warning("MCP client not connected")
            return
        
        try:
            if self.process:
                logger.info("Shutting down MCP server")
                
                # Send termination signal
                self.process.terminate()
                
                # Wait for graceful shutdown (max 5 seconds)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("MCP server did not terminate gracefully, forcing kill")
                    self.process.kill()
                    self.process.wait()
                
                self.process = None
            
            self.connected = False
            logger.info("MCP server disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting MCP server: {e}", exc_info=True)
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any], max_retries: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute an MCP tool and return results with retry logic.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments as dictionary
            max_retries: Maximum number of retries (default: from config or 3)
            
        Returns:
            Dictionary containing execution results:
            {
                "success": bool,
                "result": Any,
                "error": Optional[str],
                "duration_ms": float
            }
        """
        if not self.connected:
            return {
                "success": False,
                "error": "MCP client not connected",
                "result": None,
                "duration_ms": 0.0
            }
        
        # Get max retries from parameter, config, or default to 3
        if max_retries is None:
            max_retries = self.config.get("max_retries", 3)
        
        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(1, max_retries + 1):
            request_id = f"{tool_name}_{int(time.time() * 1000)}"
            start_time = time.time()
            
            try:
                # Format MCP protocol request
                request = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
                
                if attempt > 1:
                    logger.info(f"MCP tool {tool_name} retry attempt {attempt}/{max_retries}")
                else:
                    logger.debug(f"Sending MCP request: {tool_name} with args: {arguments}")
                
                # Send request to server
                if self.process and self.process.stdin:
                    self.process.stdin.write(json.dumps(request) + "\n")
                    self.process.stdin.flush()
                else:
                    raise RuntimeError("MCP server process stdin not available")
                
                # Wait for response with timeout (Windows-compatible)
                response_line = None
                if self.process and self.process.stdout:
                    response_line = self._read_line_with_timeout(self.process.stdout, self.timeout)
                    if response_line is None:
                        raise TimeoutError(f"MCP tool call timed out after {self.timeout}s")
                
                # Parse response
                if response_line:
                    response = json.loads(response_line)
                    
                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Check for error in response
                    if "error" in response:
                        error_msg = response["error"].get("message", "Unknown error")
                        logger.error(f"MCP tool {tool_name} failed: {error_msg}")
                        
                        # Record metrics
                        self._record_call(tool_name, duration_ms, False)
                        
                        # Store error for potential retry
                        last_error = {
                            "success": False,
                            "error": error_msg,
                            "result": None,
                            "duration_ms": duration_ms
                        }
                        
                        # Retry on error if attempts remain
                        if attempt < max_retries:
                            delay = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                            logger.warning(f"MCP tool {tool_name} failed (attempt {attempt}/{max_retries}), retrying in {delay}s")
                            time.sleep(delay)
                            continue
                        
                        return last_error
                    
                    # Extract result
                    result = response.get("result", {})
                    
                    # Record metrics
                    self._record_call(tool_name, duration_ms, True)
                    
                    logger.debug(f"MCP tool {tool_name} succeeded in {duration_ms:.2f}ms")
                    
                    return {
                        "success": True,
                        "result": result,
                        "error": None,
                        "duration_ms": duration_ms
                    }
                else:
                    raise RuntimeError("No response received from MCP server")
                    
            except TimeoutError as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(f"MCP tool {tool_name} timed out: {e}")
                self._record_call(tool_name, duration_ms, False)
                
                last_error = {
                    "success": False,
                    "error": str(e),
                    "result": None,
                    "duration_ms": duration_ms
                }
                
                # Retry on timeout if attempts remain
                if attempt < max_retries:
                    delay = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"MCP tool {tool_name} timed out (attempt {attempt}/{max_retries}), retrying in {delay}s")
                    time.sleep(delay)
                    continue
                
                return last_error
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(f"MCP tool {tool_name} failed: {e}", exc_info=True)
                self._record_call(tool_name, duration_ms, False)
                
                last_error = {
                    "success": False,
                    "error": str(e),
                    "result": None,
                    "duration_ms": duration_ms
                }
                
                # Retry on exception if attempts remain
                if attempt < max_retries:
                    delay = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"MCP tool {tool_name} failed (attempt {attempt}/{max_retries}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                    continue
                
                return last_error
        
        # Return last error if all retries exhausted
        return last_error if last_error else {
            "success": False,
            "error": "All retry attempts exhausted",
            "result": None,
            "duration_ms": 0.0
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Query available tools from MCP server.
        
        Returns:
            List of tool definitions with names, descriptions, and schemas
        """
        if not self.connected:
            logger.warning("Cannot list tools: MCP client not connected")
            return []
        
        try:
            # Format MCP protocol request for listing tools
            request = {
                "jsonrpc": "2.0",
                "id": "list_tools",
                "method": "tools/list",
                "params": {}
            }
            
            logger.debug("Requesting tool list from MCP server")
            
            # Send request
            if self.process and self.process.stdin:
                self.process.stdin.write(json.dumps(request) + "\n")
                self.process.stdin.flush()
            else:
                raise RuntimeError("MCP server process stdin not available")
            
            # Read response (Windows-compatible)
            if self.process and self.process.stdout:
                response_line = self._read_line_with_timeout(self.process.stdout, self.timeout)
                
                if response_line:
                    response = json.loads(response_line)
                    
                    # Extract tools from response
                    if "result" in response:
                        tools = response["result"].get("tools", [])
                        self.available_tools = tools
                        logger.info(f"Discovered {len(tools)} MCP tools")
                        return tools
                    else:
                        logger.error("No tools found in MCP server response")
                        return []
                else:
                    logger.error("Timeout waiting for tool list response")
                    return []
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}", exc_info=True)
            return []
    
    def _validate_critical_tools(self, tools: List[Dict[str, Any]]) -> bool:
        """
        Validate that critical tools are available.
        
        Args:
            tools: List of available tools from list_tools()
            
        Returns:
            True if all critical tools present, False otherwise
        """
        # Define critical tools required for operation
        critical_tools = [
            "playwright_navigate",
            "playwright_click",
            "playwright_fill",
            "playwright_evaluate"
        ]
        
        # Extract tool names from tools list
        available_tool_names = [tool.get("name", "") for tool in tools]
        
        # Check for missing critical tools
        missing_tools = [tool for tool in critical_tools if tool not in available_tool_names]
        
        if missing_tools:
            logger.warning(f"Missing critical MCP tools: {', '.join(missing_tools)}")
            logger.warning(f"Available tools: {', '.join(available_tool_names)}")
            return False
        
        logger.info(f"All critical MCP tools validated: {', '.join(critical_tools)}")
        return True
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get MCP operation metrics.
        
        Returns:
            Dictionary containing:
            - total_calls: Total number of tool calls
            - total_errors: Total number of errors
            - error_rate: Overall error rate percentage
            - average_latency_ms: Average latency across all calls
            - p95_latency_ms: 95th percentile latency
            - p99_latency_ms: 99th percentile latency
            - per_tool_metrics: Metrics broken down by tool
        """
        with self.metrics_lock:
            # Calculate overall metrics
            all_latencies = []
            for metrics in self.tool_metrics.values():
                all_latencies.extend(metrics.latencies)
            
            # Calculate percentiles
            p95_latency = 0.0
            p99_latency = 0.0
            avg_latency = 0.0
            
            if all_latencies:
                sorted_latencies = sorted(all_latencies)
                p95_index = int(len(sorted_latencies) * 0.95)
                p99_index = int(len(sorted_latencies) * 0.99)
                p95_latency = sorted_latencies[min(p95_index, len(sorted_latencies) - 1)]
                p99_latency = sorted_latencies[min(p99_index, len(sorted_latencies) - 1)]
                avg_latency = sum(all_latencies) / len(all_latencies)
            
            # Calculate error rate
            error_rate = 0.0
            if self.total_calls > 0:
                error_rate = (self.total_errors / self.total_calls) * 100
            
            # Build per-tool metrics
            per_tool = {}
            for tool_name, metrics in self.tool_metrics.items():
                per_tool[tool_name] = {
                    "call_count": metrics.call_count,
                    "error_count": metrics.error_count,
                    "error_rate": metrics.get_error_rate(),
                    "average_latency_ms": metrics.get_average_latency(),
                    "p95_latency_ms": metrics.get_percentile(95),
                    "p99_latency_ms": metrics.get_percentile(99)
                }
            
            return {
                "total_calls": self.total_calls,
                "total_errors": self.total_errors,
                "error_rate": error_rate,
                "average_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "p99_latency_ms": p99_latency,
                "per_tool_metrics": per_tool
            }
    
    @staticmethod
    def _read_line_with_timeout(stream, timeout_seconds: float) -> Optional[str]:
        """
        Read a line from a stream with timeout (Windows-compatible).
        
        Uses a background thread since select.select() doesn't work on
        Windows pipes.
        
        Args:
            stream: File-like object to read from
            timeout_seconds: Maximum seconds to wait
            
        Returns:
            The line read, or None on timeout
        """
        result_queue = queue.Queue()
        
        def _reader():
            try:
                line = stream.readline()
                result_queue.put(line)
            except Exception as e:
                result_queue.put(None)
        
        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()
        
        try:
            return result_queue.get(timeout=timeout_seconds)
        except queue.Empty:
            return None
    
    def _record_call(self, tool_name: str, duration_ms: float, success: bool):
        """
        Record a tool call for metrics tracking.
        
        Args:
            tool_name: Name of the tool called
            duration_ms: Duration of the call in milliseconds
            success: Whether the call succeeded
        """
        with self.metrics_lock:
            self.total_calls += 1
            if not success:
                self.total_errors += 1
            
            # Record per-tool metrics
            self.tool_metrics[tool_name].add_call(duration_ms, success)
    
    @staticmethod
    def pretty_print_response(response: Dict[str, Any]) -> str:
        """
        Format MCP JSON-RPC response for human-readable logging.
        
        Args:
            response: JSON-RPC response dictionary
            
        Returns:
            Formatted multi-line string representation
        """
        import json
        from datetime import datetime
        
        lines = []
        lines.append("=" * 60)
        lines.append("MCP JSON-RPC Response")
        lines.append("=" * 60)
        lines.append(f"Timestamp: {datetime.now().isoformat()}")
        lines.append("")
        
        # Request ID
        if "id" in response:
            lines.append(f"Request ID: {response['id']}")
        
        # JSON-RPC version
        if "jsonrpc" in response:
            lines.append(f"JSON-RPC Version: {response['jsonrpc']}")
        
        lines.append("")
        
        # Result or Error
        if "result" in response:
            lines.append("Status: SUCCESS")
            lines.append("")
            lines.append("Result:")
            lines.append(json.dumps(response["result"], indent=2))
        elif "error" in response:
            error = response["error"]
            lines.append("Status: ERROR")
            lines.append("")
            lines.append(f"Error Code: {error.get('code', 'N/A')}")
            lines.append(f"Error Message: {error.get('message', 'N/A')}")
            if "data" in error:
                lines.append("Error Data:")
                lines.append(json.dumps(error["data"], indent=2))
        else:
            lines.append("Status: UNKNOWN (no result or error)")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
