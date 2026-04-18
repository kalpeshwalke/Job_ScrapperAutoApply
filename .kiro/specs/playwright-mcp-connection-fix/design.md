# Playwright MCP Connection Fix - Bugfix Design

## Overview

The Playwright MCP (Model Context Protocol) server connection fails immediately after initialization with error code -32000 ("Connection closed"). The root cause is that the `MCPClient` implementation spawns the MCP server process but does not perform the required MCP protocol initialization handshake. The MCP protocol requires an `initialize` request to be sent after the server starts, followed by an `initialized` notification. Without this handshake, the server closes the connection immediately.

This fix will implement the proper MCP protocol initialization sequence to establish and maintain a stable connection with the Playwright MCP server.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when the MCP client attempts to connect to the Playwright MCP server without performing the protocol initialization handshake
- **Property (P)**: The desired behavior when connecting to the MCP server - the connection should remain open and functional after initialization
- **Preservation**: Existing non-MCP functionality and other MCP operations that must remain unchanged by the fix
- **MCPClient**: The client class in `src/ai_auto_apply/core/mcp_client.py` that manages communication with the Playwright MCP server
- **MCP Protocol**: The Model Context Protocol specification that defines the initialization handshake sequence (initialize request → initialize response → initialized notification)
- **Initialization Handshake**: The required sequence of messages to establish an MCP connection: client sends `initialize` request, server responds with capabilities, client sends `initialized` notification

## Bug Details

### Bug Condition

The bug manifests when the `MCPClient.connect()` method spawns the Playwright MCP server process but fails to perform the MCP protocol initialization handshake. The server expects an `initialize` request immediately after startup, but the client only calls `list_tools()` which sends a `tools/list` request. This violates the MCP protocol specification, causing the server to close the connection with error -32000.

**Formal Specification:**
```
FUNCTION isBugCondition(connection_attempt)
  INPUT: connection_attempt of type MCPConnectionAttempt
  OUTPUT: boolean
  
  RETURN connection_attempt.server_spawned = true
         AND connection_attempt.initialize_request_sent = false
         AND connection_attempt.list_tools_called = true
         AND connection_attempt.connection_closed = true
END FUNCTION
```

### Examples

- **Example 1**: Client spawns MCP server → immediately calls `list_tools()` → server closes connection with error -32000
  - **Expected**: Client spawns MCP server → sends `initialize` request → receives capabilities → sends `initialized` notification → connection stays open
  
- **Example 2**: Client spawns MCP server → waits 2 seconds → calls `list_tools()` → server closes connection
  - **Expected**: Client spawns MCP server → performs handshake → connection stays open → `list_tools()` succeeds

- **Example 3**: Client attempts to call any MCP tool without initialization → connection closed
  - **Expected**: Client performs initialization handshake first → connection stays open → tool calls succeed

- **Edge Case**: Client spawns MCP server but server process fails to start → connection should fail gracefully with clear error message
  - **Expected**: Client detects server startup failure and returns appropriate error without attempting handshake

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Non-MCP Playwright operations (direct Playwright usage without MCP) must continue to work exactly as before
- Other MCP server connections (if any non-Playwright MCP servers are added in the future) must continue to work
- MCP connection logging and error reporting must continue to provide detailed diagnostic information
- AI auto-apply system functionality without MCP integration must continue to work normally

**Scope:**
All operations that do NOT involve the Playwright MCP server initialization should be completely unaffected by this fix. This includes:
- Direct Playwright browser automation (non-MCP)
- AI provider interactions
- FSM orchestrator workflow
- DOM toolkit operations
- Career page validation
- Excel file operations

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **Missing MCP Protocol Handshake**: The `MCPClient.connect()` method spawns the MCP server process but does not implement the required initialization sequence defined by the MCP protocol specification
   - The MCP protocol requires: `initialize` request → server response with capabilities → `initialized` notification
   - Current implementation skips directly to `list_tools()` which sends a `tools/list` request
   - The server expects the handshake first and closes the connection when it doesn't receive it

2. **Incorrect Assumption About Server Readiness**: The code assumes the server is ready to accept tool requests immediately after spawning
   - Current code: spawn process → wait 2 seconds → call `list_tools()`
   - Correct flow: spawn process → send `initialize` → wait for response → send `initialized` → then call `list_tools()`

3. **No Protocol Version Negotiation**: The client doesn't specify which MCP protocol version it supports
   - The `initialize` request should include `protocolVersion` and `capabilities`
   - Without this, the server cannot determine compatibility

4. **Missing Client Capabilities Declaration**: The client doesn't declare its capabilities to the server
   - The server needs to know what features the client supports
   - This is communicated in the `initialize` request

## Correctness Properties

Property 1: Bug Condition - MCP Connection Establishment

_For any_ connection attempt where the MCP server process is spawned successfully, the fixed `MCPClient.connect()` method SHALL perform the complete MCP protocol initialization handshake (send `initialize` request, receive server capabilities, send `initialized` notification) and maintain an open, functional connection that can successfully execute tool calls.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-MCP Functionality

_For any_ operation that does NOT involve the Playwright MCP server initialization (direct Playwright usage, other MCP servers, AI operations, FSM workflow), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for non-MCP operations.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/ai_auto_apply/core/mcp_client.py`

**Function**: `connect()`

**Specific Changes**:

1. **Add MCP Protocol Initialization Method**: Create a new private method `_initialize_protocol()` that performs the handshake
   - Send `initialize` request with protocol version and client capabilities
   - Wait for server response with timeout
   - Parse server capabilities from response
   - Send `initialized` notification to complete handshake
   - Return success/failure status

2. **Modify connect() Method**: Update the connection sequence to include protocol initialization
   - After spawning the server process and verifying it's running
   - Call `_initialize_protocol()` before calling `list_tools()`
   - Handle initialization failures gracefully with appropriate error messages
   - Only proceed to tool discovery if initialization succeeds

3. **Add Protocol Version Constant**: Define the MCP protocol version the client supports
   - Add constant: `MCP_PROTOCOL_VERSION = "2024-11-05"` (or latest stable version)
   - Use this in the `initialize` request

4. **Add Client Capabilities Declaration**: Define what features the client supports
   - Declare support for tool execution
   - Declare any other relevant capabilities (sampling, prompts, resources, etc.)
   - Include in the `initialize` request

5. **Improve Error Handling**: Add specific error messages for initialization failures
   - Distinguish between server spawn failures and protocol initialization failures
   - Log the specific step where initialization failed
   - Provide actionable error messages (e.g., "MCP server started but failed to respond to initialize request")

### Implementation Pseudocode

```python
def _initialize_protocol(self) -> bool:
    """
    Perform MCP protocol initialization handshake.
    
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
        
        # Send request
        self.process.stdin.write(json.dumps(initialize_request) + "\n")
        self.process.stdin.flush()
        
        # Step 2: Wait for initialize response
        response_line = self._read_line_with_timeout(self.process.stdout, self.timeout)
        
        if not response_line:
            logger.error("MCP server did not respond to initialize request")
            return False
        
        response = json.loads(response_line)
        
        # Check for error in response
        if "error" in response:
            error_msg = response["error"].get("message", "Unknown error")
            logger.error(f"MCP initialization failed: {error_msg}")
            return False
        
        # Extract server capabilities
        server_capabilities = response.get("result", {}).get("capabilities", {})
        logger.info(f"MCP server capabilities: {server_capabilities}")
        
        # Step 3: Send initialized notification
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        
        self.process.stdin.write(json.dumps(initialized_notification) + "\n")
        self.process.stdin.flush()
        
        logger.info("MCP protocol initialization completed successfully")
        return True
        
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
        
        # NEW: Perform MCP protocol initialization handshake
        if not self._initialize_protocol():
            logger.error("MCP protocol initialization failed")
            # Clean up the process
            self.process.terminate()
            self.process.wait(timeout=5)
            return False
        
        self.connected = True
        logger.info("MCP server connection established")
        
        # Discover available tools
        self.list_tools()
        
        return True
        
    except FileNotFoundError as e:
        logger.error(f"MCP server command not found: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to connect to MCP server: {e}", exc_info=True)
        return False
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that attempt to connect to the MCP server and verify the connection closes immediately. Run these tests on the UNFIXED code to observe failures and confirm the root cause is missing protocol initialization.

**Test Cases**:
1. **Connection Without Handshake Test**: Spawn MCP server and immediately call `list_tools()` without initialization (will fail on unfixed code with error -32000)
2. **Tool Call Without Initialization Test**: Spawn MCP server and attempt to call a tool without initialization (will fail on unfixed code)
3. **Server Response Monitoring Test**: Monitor server stdout/stderr to verify it's waiting for `initialize` request (will show server closes connection on unfixed code)
4. **Protocol Violation Detection Test**: Verify that sending `tools/list` before `initialize` causes connection closure (will fail on unfixed code)

**Expected Counterexamples**:
- Connection closes immediately with error -32000 when `list_tools()` is called without prior initialization
- Possible causes: missing `initialize` request, missing `initialized` notification, incorrect protocol version

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (attempting to connect to MCP server), the fixed function produces the expected behavior (successful connection with proper handshake).

**Pseudocode:**
```
FOR ALL connection_attempt WHERE isBugCondition(connection_attempt) DO
  result := connect_fixed()
  ASSERT result.connection_established = true
  ASSERT result.handshake_completed = true
  ASSERT result.tools_discoverable = true
END FOR
```

**Test Cases**:
1. **Successful Connection Test**: Verify `connect()` performs handshake and maintains open connection
2. **Tool Discovery After Handshake Test**: Verify `list_tools()` succeeds after proper initialization
3. **Tool Execution Test**: Verify tool calls work after successful connection
4. **Multiple Connection Attempts Test**: Verify reconnection works if connection is closed and reopened

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (non-MCP operations), the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL operation WHERE NOT isBugCondition(operation) DO
  ASSERT originalBehavior(operation) = fixedBehavior(operation)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-MCP operations, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Non-MCP Playwright Operations**: Verify direct Playwright usage (without MCP) continues to work correctly
2. **AI Provider Operations**: Verify AI provider interactions are unaffected by MCP changes
3. **FSM Orchestrator Workflow**: Verify FSM workflow operates correctly with or without MCP enabled
4. **Configuration Loading**: Verify MCP configuration loading and validation continues to work

### Unit Tests

- Test `_initialize_protocol()` method in isolation with mocked server responses
- Test `connect()` method with successful and failed initialization scenarios
- Test error handling for various failure modes (server not found, server crashes, timeout, protocol errors)
- Test that connection state is properly tracked (connected flag, process handle)
- Test cleanup on connection failure (process termination, resource cleanup)

### Property-Based Tests

- Generate random MCP server configurations and verify connection succeeds with proper handshake
- Generate random sequences of MCP operations and verify protocol compliance
- Test that all tool calls succeed after successful initialization across many scenarios
- Verify connection remains stable under various load patterns

### Integration Tests

- Test full MCP workflow: connect → initialize → discover tools → execute tool → disconnect
- Test MCP integration with FSM orchestrator in auto-apply workflow
- Test error recovery: connection failure → retry → successful connection
- Test that MCP-disabled mode continues to work (fallback to direct Playwright)
- Test concurrent MCP operations (if multiple clients are supported)
