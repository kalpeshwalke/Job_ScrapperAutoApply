# Implementation Plan: Complete MCP Integration

## Overview

This implementation plan transforms the AI auto-apply system from rigid pattern-based automation to an adaptive, intelligent system by completing the MCP (Model Context Protocol) integration. The tasks are organized to build incrementally, starting with core infrastructure (MCP client initialization and injection), then enabling AI-driven capabilities (page analysis and action execution), and finally replacing hardcoded components with intelligent alternatives.

## Tasks

- [x] 1. Initialize MCP client in FSM Orchestrator
  - [x] 1.1 Add MCP client initialization method to FSM Orchestrator
    - Create `_initialize_mcp_client()` method that reads MCP config from `self.config.get("mcp", {})`
    - Check if `mcp.enabled` is True, return None if disabled
    - Create MCPClient instance with mcp_config
    - Call `mcp_client.connect()` and return client if successful, None otherwise
    - Add error handling with logging for connection failures
    - _Requirements: 1.1, 1.2, 1.3, 1.5_
  
  - [x] 1.2 Add MCP client shutdown method to FSM Orchestrator
    - Create `_shutdown_mcp_client()` method that calls `self.mcp_client.disconnect()` if client exists
    - Add error handling with logging for disconnection errors
    - _Requirements: 1.4_
  
  - [x] 1.3 Integrate MCP client lifecycle into FSM Orchestrator constructor
    - Call `_initialize_mcp_client()` in `__init__` and store result in `self.mcp_client`
    - Add logging to indicate MCP enabled/disabled status
    - _Requirements: 1.1, 1.2, 1.5_
  
  - [ ]* 1.4 Write unit tests for MCP client initialization
    - Test successful MCP initialization when enabled
    - Test MCP initialization returns None when disabled
    - Test MCP initialization handles connection failures gracefully
    - Test MCP shutdown cleans up resources
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Inject MCP client into agents
  - [x] 2.1 Update Planner Agent constructor to accept MCP client
    - Add `mcp_client` parameter to `PlannerAgent.__init__` with default None
    - Store `self.mcp_client = mcp_client`
    - Set `self.mcp_enabled = mcp_client is not None`
    - Add logging to indicate MCP mode (enabled/disabled)
    - _Requirements: 2.1, 2.3, 2.5_
  
  - [x] 2.2 Update Browser Agent constructor to accept MCP client
    - Add `mcp_client` parameter to `BrowserAgent.__init__` with default None
    - Store `self.mcp_client = mcp_client`
    - Set `self.mcp_enabled = mcp_client is not None`
    - Add logging to indicate MCP mode (enabled/disabled)
    - _Requirements: 2.2, 2.4, 2.6_
  
  - [x] 2.3 Update FSM Orchestrator to pass MCP client to agents
    - Modify Planner Agent instantiation to pass `mcp_client=self.mcp_client`
    - Modify Browser Agent instantiation to pass `mcp_client=self.mcp_client`
    - _Requirements: 2.1, 2.2_
  
  - [ ]* 2.4 Write unit tests for MCP client injection
    - Test Planner Agent with MCP client sets mcp_enabled=True
    - Test Planner Agent without MCP client sets mcp_enabled=False
    - Test Browser Agent with MCP client sets mcp_enabled=True
    - Test Browser Agent without MCP client sets mcp_enabled=False
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 3. Implement MCP tool discovery and validation
  - [x] 3.1 Add tool discovery to MCP client connect method
    - After successful connection, call `self.list_tools()` to discover available tools
    - Store discovered tools in `self.available_tools`
    - Log the list of available tools for verification
    - _Requirements: 8.1, 8.2_
  
  - [x] 3.2 Add tool validation to MCP client
    - Define list of critical tools: `["playwright_navigate", "playwright_click", "playwright_fill", "playwright_evaluate"]`
    - Check if all critical tools are in `self.available_tools`
    - Log warning if any critical tools are missing
    - Return False from `connect()` if critical tools are missing
    - _Requirements: 8.3, 8.4, 8.5_
  
  - [ ]* 3.3 Write unit tests for tool discovery and validation
    - Test tool discovery succeeds and logs available tools
    - Test tool validation passes when all critical tools present
    - Test tool validation fails when critical tools missing
    - Test connection fails when tool discovery fails
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement AI-driven page analysis in Planner Agent
  - [x] 5.1 Add MCP-based page analysis method to Planner Agent
    - Create `analyze_page_with_mcp(current_url: str) -> Dict[str, Any]` method
    - Return empty dict if MCP not enabled
    - Use `self.mcp_client.call_tool("playwright_evaluate", {"expression": careers_query})` to query for careers links
    - Parse result and extract careers links with text, href, visible, inNav properties
    - Return dict with "careers_links" key containing list of link dicts
    - Add error handling with logging for MCP failures
    - _Requirements: 3.1, 3.2, 3.6_
  
  - [x] 5.2 Add careers link selection logic to Planner Agent
    - Create `select_best_careers_link(careers_links: List[Dict]) -> Optional[Dict]` method
    - Score each link based on text matching ("careers", "jobs", "join"), navigation position, and visibility
    - Return highest scoring link or None if no links
    - _Requirements: 4.2, 4.3, 4.4_
  
  - [x] 5.3 Integrate MCP page analysis into plan_next_step
    - Check if `self.mcp_enabled and self.mcp_client` at start of `plan_next_step`
    - Call `self.analyze_page_with_mcp(dom_state.get("url", ""))` to get page analysis
    - Add page analysis to context dict as `context["mcp_analysis"] = page_analysis`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [ ]* 5.4 Write unit tests for page analysis
    - Test analyze_page_with_mcp returns empty dict when MCP disabled
    - Test analyze_page_with_mcp calls MCP tool with correct query
    - Test analyze_page_with_mcp parses careers links correctly
    - Test select_best_careers_link scores and ranks links correctly
    - Test select_best_careers_link handles empty list
    - _Requirements: 3.1, 3.2, 3.3, 4.2, 4.3, 4.4_

- [x] 6. Implement MCP-based action execution in Browser Agent
  - [x] 6.1 Add MCP action execution method to Browser Agent
    - Create `_execute_step_mcp(step: str, dom_state: Dict, job_data: Dict) -> Dict` method
    - Parse step to determine action type (click, fill, navigate)
    - For "click" actions: extract selector and call `playwright_click`
    - For "fill" actions: extract selector and value, call `playwright_fill`
    - For "navigate" actions: extract URL and call `playwright_navigate`
    - Return dict with success, action_summary, and error fields
    - Add error handling with logging for MCP failures
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [x] 6.2 Add helper methods for extracting action parameters
    - Create `_extract_selector_from_step(step: str, dom_state: Dict) -> Optional[str]` method
    - Create `_extract_fill_params(step: str, dom_state: Dict, job_data: Dict) -> Tuple[Optional[str], Optional[str]]` method
    - Create `_extract_url_from_step(step: str) -> Optional[str]` method
    - Use pattern matching and DOM state to extract parameters from step descriptions
    - _Requirements: 5.1, 5.2, 5.3_
  
  - [x] 6.3 Integrate MCP execution into execute_step method
    - Check if `should_use_mcp and self.mcp_client` at start of `execute_step`
    - Call `_execute_step_mcp` if MCP enabled
    - If MCP execution succeeds, return result
    - If MCP execution fails and fallback enabled, call `_execute_step_legacy`
    - If MCP execution fails and fallback disabled, return MCP error
    - Add logging for MCP execution and fallback decisions
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.2, 7.3_
  
  - [ ]* 6.4 Write unit tests for MCP action execution
    - Test _execute_step_mcp handles click actions correctly
    - Test _execute_step_mcp handles fill actions correctly
    - Test _execute_step_mcp handles navigate actions correctly
    - Test _execute_step_mcp returns error for unrecognized actions
    - Test execute_step uses MCP when enabled
    - Test execute_step falls back to legacy on MCP failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.2_

- [x] 7. Implement AI-driven homepage navigation
  - [x] 7.1 Add AI-driven navigation method to FSM Orchestrator
    - Create `_ai_driven_homepage_navigation(job_data: Dict) -> bool` method
    - Implement retry loop with max_attempts=3
    - For each attempt: analyze page with MCP, select best careers link, execute navigation, verify destination
    - Use `self.planner.analyze_page_with_mcp(self.page.url)` for page analysis
    - Use `self.planner.select_best_careers_link(careers_links)` for link selection
    - Use `self.mcp_client.call_tool("playwright_click", {"selector": ...})` for navigation
    - Wait for navigation to complete (sleep 3 seconds)
    - Call `_verify_careers_page_with_mcp()` to verify destination
    - Return True if successful, False after all attempts exhausted
    - Add logging for each step and attempt
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 6.1, 6.2, 6.3_
  
  - [x] 7.2 Add careers page verification method to FSM Orchestrator
    - Create `_verify_careers_page_with_mcp() -> bool` method
    - Use MCP playwright_evaluate to query page for job indicators (job links, form fields, page title, URL)
    - Check if page has job-related indicators: jobLinks >= 3, formFields >= 3, or "career"/"job" in URL
    - Return True if indicators present, False otherwise
    - Add error handling with logging for MCP failures
    - _Requirements: 6.4_
  
  - [x] 7.3 Integrate AI-driven navigation into apply_to_job workflow
    - In `apply_to_job` method, detect homepage redirect scenario
    - If homepage redirect and `self.mcp_client` exists, call `_ai_driven_homepage_navigation(job_data)`
    - If homepage redirect and no MCP client, call `_legacy_homepage_navigation(job_data)` (existing HomepageNavigator)
    - Handle navigation result and continue workflow or fail appropriately
    - Add logging for navigation mode selection
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_
  
  - [ ]* 7.4 Write unit tests for AI-driven navigation
    - Test _ai_driven_homepage_navigation succeeds on first attempt
    - Test _ai_driven_homepage_navigation retries on failure
    - Test _ai_driven_homepage_navigation returns False after max attempts
    - Test _verify_careers_page_with_mcp detects careers pages correctly
    - Test apply_to_job uses AI navigation when MCP enabled
    - Test apply_to_job uses legacy navigation when MCP disabled
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement MCP error handling and retry logic
  - [x] 9.1 Add retry logic to MCP client call_tool method
    - Wrap existing `call_tool` implementation with retry loop
    - Use exponential backoff: 2s, 4s, 8s delays between retries
    - Default max_retries=3 from config or parameter
    - Log each retry attempt with attempt number and delay
    - Return last failed result after all retries exhausted
    - _Requirements: 9.1, 9.4_
  
  - [x] 9.2 Add MCP error handling to Browser Agent
    - In `_execute_step_mcp`, catch all exceptions and return error dict
    - Log error type, message, and context (tool name, arguments, URL)
    - Include error details in returned dict for upstream handling
    - _Requirements: 9.2, 9.5_
  
  - [x] 9.3 Add MCP connection recovery to Browser Agent
    - In `execute_step`, detect MCP connection lost errors
    - Attempt to reconnect once by calling `self.mcp_client.connect()`
    - If reconnect succeeds, retry the operation
    - If reconnect fails, fall back to legacy mode
    - Log connection recovery attempts and results
    - _Requirements: 9.3_
  
  - [ ]* 9.4 Write unit tests for error handling and retry
    - Test call_tool retries on timeout with exponential backoff
    - Test call_tool returns last error after max retries
    - Test _execute_step_mcp catches and logs exceptions
    - Test execute_step attempts reconnection on connection lost
    - Test execute_step falls back to legacy after reconnection fails
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 10. Implement MCP configuration validation
  - [x] 10.1 Add configuration schema validation
    - Create configuration schema dict with required fields and types
    - Validate `mcp.enabled` is boolean
    - Validate `mcp.command` is string when enabled
    - Validate `mcp.args` is list when enabled
    - Validate `mcp.timeout` is positive integer
    - Validate `mcp.fallback_to_legacy` is boolean
    - Log validation errors with specific field and expected type
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [x] 10.2 Integrate configuration validation into FSM Orchestrator
    - Call configuration validation in `_initialize_mcp_client` before creating client
    - Return None if validation fails
    - Log validation errors for debugging
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  
  - [ ]* 10.3 Write unit tests for configuration validation
    - Test validation passes with valid configuration
    - Test validation fails when mcp.enabled is not boolean
    - Test validation fails when mcp.command is missing
    - Test validation fails when mcp.timeout is negative
    - Test _initialize_mcp_client returns None on validation failure
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 11. Implement comprehensive logging for MCP operations
  - [x] 11.1 Add MCP tool call logging
    - Log tool name, arguments (sanitized), and timestamp before each call
    - Log result status, duration, and error message after each call
    - Use structured logging format for easy parsing
    - Sanitize sensitive data (passwords, personal info) from logs
    - _Requirements: 11.1, 11.2_
  
  - [x] 11.2 Add MCP decision logging to Planner Agent
    - Log decision rationale when selecting careers links
    - Log page analysis results (number of links found, scores)
    - Log navigation strategy decisions
    - _Requirements: 11.3_
  
  - [x] 11.3 Add MCP fallback logging
    - Log reason for fallback (MCP error, timeout, connection lost)
    - Log context (current URL, action being attempted)
    - Log whether fallback succeeded or failed
    - _Requirements: 11.4_
  
  - [x] 11.4 Add MCP metrics to StructuredLogger
    - Track MCP tool call counts by tool name
    - Track MCP success rates by tool name
    - Track MCP latencies (min, max, avg) by tool name
    - Track fallback counts and reasons
    - Include MCP metrics in final metrics report
    - _Requirements: 11.5, 11.6_
  
  - [ ]* 11.5 Write unit tests for MCP logging
    - Test tool call logging includes all required fields
    - Test sensitive data is sanitized from logs
    - Test decision logging captures rationale
    - Test fallback logging captures reason and context
    - Test metrics tracking accumulates correctly
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 12. Implement MCP response parsing and pretty printing
  - [x] 12.1 Add JSON-RPC response parsing to MCP client
    - Parse JSON-RPC response structure (id, result, error)
    - Extract error code and message from error responses
    - Extract result data from success responses
    - Handle invalid JSON with error logging and parse error return
    - _Requirements: 12.1, 12.2, 12.3, 12.5_
  
  - [x] 12.2 Add pretty printing method to MCP client
    - Create `pretty_print_response(response: Dict) -> str` method
    - Format response as human-readable multi-line string
    - Include all relevant fields (id, result/error, timestamp)
    - Use indentation and structure for readability
    - _Requirements: 12.4_
  
  - [ ]* 12.3 Write property test for round-trip parsing and printing
    - **Property 1: Round-trip consistency**
    - **Validates: Requirements 12.6**
    - Generate random valid MCP responses
    - Parse response, pretty print, parse again
    - Verify original and final parsed objects are equivalent
    - _Requirements: 12.6_
  
  - [ ]* 12.4 Write unit tests for response parsing
    - Test parsing success responses extracts result correctly
    - Test parsing error responses extracts error code and message
    - Test parsing invalid JSON returns parse error
    - Test pretty printing formats responses readably
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Integration and documentation
  - [x] 14.1 Update configuration documentation
    - Document all MCP configuration options in README or config comments
    - Provide example configurations for common scenarios
    - Document fallback behavior and when it triggers
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  
  - [x] 14.2 Add MCP integration examples
    - Create example showing MCP-enabled configuration
    - Create example showing MCP-disabled (legacy) configuration
    - Create example showing hybrid mode with fallback
    - _Requirements: 7.1, 7.3, 7.4, 7.5_
  
  - [ ]* 14.3 Write integration tests for end-to-end MCP workflow
    - Test complete job application with MCP enabled
    - Test homepage navigation with AI-driven approach
    - Test form filling with MCP tools
    - Test fallback to legacy mode on MCP failure
    - Test MCP disabled configuration uses legacy mode exclusively
    - _Requirements: 1.1, 2.1, 2.2, 3.1, 4.1, 5.1, 6.1, 7.1, 7.2, 7.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- MCP integration is designed with graceful fallback to legacy mode
- All MCP operations include comprehensive error handling and logging
- Configuration validation ensures system fails fast with clear error messages
