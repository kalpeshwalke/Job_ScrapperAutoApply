# Requirements Document

## Introduction

The AI auto-apply system currently has an MCP (Model Context Protocol) client that can connect to the Playwright MCP server, but the FSM orchestrator and agents do not use it. Instead, they rely on hardcoded automation with keyword matching for navigation, which fails when website structures don't match expected patterns. This feature will complete the MCP integration by enabling AI-driven decision-making for all browser interactions, making the system adaptive and intelligent rather than rigid and pattern-based.

## Glossary

- **MCP_Client**: The client class that manages communication with the Playwright MCP server via JSON-RPC protocol
- **FSM_Orchestrator**: The finite state machine orchestrator that coordinates the job application workflow
- **Planner_Agent**: The high-level AI agent that decides what actions to take based on page state
- **Browser_Agent**: The low-level agent that executes browser interactions (clicks, form fills, etc.)
- **Homepage_Navigator**: The current hardcoded component that uses keyword matching to find careers links
- **MCP_Tools**: Playwright browser automation tools exposed through the MCP protocol (navigate, click, fill, screenshot, evaluate)
- **AI_Driven_Navigation**: Navigation decisions made by AI analyzing page content rather than hardcoded keyword matching
- **Adaptive_System**: A system that can understand and respond to different website structures without hardcoded patterns

## Requirements

### Requirement 1: MCP Client Initialization in FSM Orchestrator

**User Story:** As a system architect, I want the FSM orchestrator to initialize and manage the MCP client connection, so that MCP tools are available throughout the application workflow.

#### Acceptance Criteria

1. WHEN the FSM_Orchestrator is initialized, THE FSM_Orchestrator SHALL create an MCP_Client instance using the MCP configuration from the config file
2. WHEN the MCP_Client is created, THE FSM_Orchestrator SHALL call the connect() method to establish connection with the Playwright MCP server
3. IF the MCP connection fails, THEN THE FSM_Orchestrator SHALL log the error and continue with legacy automation mode
4. WHEN the FSM_Orchestrator completes a job application, THE FSM_Orchestrator SHALL disconnect the MCP_Client to clean up resources
5. WHEN MCP is disabled in configuration, THE FSM_Orchestrator SHALL skip MCP_Client initialization and use legacy mode

### Requirement 2: MCP Client Injection into Agents

**User Story:** As a developer, I want the Planner and Browser agents to receive the MCP client instance, so that they can use MCP tools for browser automation.

#### Acceptance Criteria

1. WHEN the FSM_Orchestrator creates the Planner_Agent, THE FSM_Orchestrator SHALL pass the MCP_Client instance as a constructor parameter
2. WHEN the FSM_Orchestrator creates the Browser_Agent, THE FSM_Orchestrator SHALL pass the MCP_Client instance as a constructor parameter
3. WHEN the Planner_Agent is initialized with an MCP_Client, THE Planner_Agent SHALL store the client reference for use in planning decisions
4. WHEN the Browser_Agent is initialized with an MCP_Client, THE Browser_Agent SHALL store the client reference for use in executing actions
5. WHEN MCP_Client is None (MCP disabled), THE Planner_Agent SHALL operate in legacy mode without MCP tools
6. WHEN MCP_Client is None (MCP disabled), THE Browser_Agent SHALL operate in legacy mode using DOM_Toolkit

### Requirement 3: AI-Driven Page Analysis Using MCP

**User Story:** As an AI agent, I want to analyze page content using MCP tools, so that I can understand the page structure and make intelligent navigation decisions.

#### Acceptance Criteria

1. WHEN the Planner_Agent needs to understand page structure, THE Planner_Agent SHALL use MCP playwright_evaluate tool to query page elements and content
2. WHEN analyzing a page for careers links, THE Planner_Agent SHALL use MCP tools to read link text, href attributes, and surrounding context
3. WHEN the page contains multiple navigation options, THE Planner_Agent SHALL use MCP tools to analyze all options and select the most relevant one
4. WHEN the Planner_Agent detects a job board structure, THE Planner_Agent SHALL use MCP tools to identify job listings and pagination controls
5. WHEN the Planner_Agent detects a form structure, THE Planner_Agent SHALL use MCP tools to identify form fields and their labels
6. FOR ALL page analysis operations, THE Planner_Agent SHALL use MCP tools to gather information rather than relying on pre-extracted DOM state

### Requirement 4: AI-Driven Navigation Decisions

**User Story:** As an AI agent, I want to make navigation decisions based on page context and understanding, so that I can successfully navigate to careers pages regardless of website structure.

#### Acceptance Criteria

1. WHEN the Planner_Agent needs to navigate from a homepage to a careers page, THE Planner_Agent SHALL analyze the page content using MCP tools to identify the best navigation path
2. WHEN multiple links could lead to careers pages, THE Planner_Agent SHALL evaluate each option's context (surrounding text, link position, semantic meaning) to select the best one
3. WHEN a careers link is in an unexpected location (footer, sidebar, dropdown menu), THE Planner_Agent SHALL still identify it through contextual analysis
4. WHEN the careers link text doesn't match common keywords (e.g., "Join Our Team" instead of "Careers"), THE Planner_Agent SHALL identify it through semantic understanding
5. IF no direct careers link exists, THEN THE Planner_Agent SHALL identify alternative navigation paths (search functionality, company info pages, etc.)
6. WHEN navigation fails, THE Planner_Agent SHALL analyze the failure reason and attempt alternative strategies

### Requirement 5: MCP-Based Action Execution

**User Story:** As a browser automation agent, I want to execute all browser actions using MCP tools, so that actions are performed reliably through the Playwright MCP server.

#### Acceptance Criteria

1. WHEN the Browser_Agent needs to click an element, THE Browser_Agent SHALL use the MCP playwright_click tool with the appropriate selector
2. WHEN the Browser_Agent needs to fill a form field, THE Browser_Agent SHALL use the MCP playwright_fill tool with the field selector and value
3. WHEN the Browser_Agent needs to navigate to a URL, THE Browser_Agent SHALL use the MCP playwright_navigate tool
4. WHEN the Browser_Agent needs to capture page state for debugging, THE Browser_Agent SHALL use the MCP playwright_screenshot tool
5. WHEN the Browser_Agent needs to execute custom JavaScript, THE Browser_Agent SHALL use the MCP playwright_evaluate tool
6. FOR ALL browser actions, THE Browser_Agent SHALL use MCP tools instead of direct Playwright API calls when MCP is enabled

### Requirement 6: Replace Hardcoded Homepage Navigator

**User Story:** As a system architect, I want to replace the hardcoded HomepageNavigator with AI-driven navigation using MCP, so that the system can adapt to any website structure.

#### Acceptance Criteria

1. WHEN the FSM_Orchestrator detects a homepage redirect, THE FSM_Orchestrator SHALL delegate navigation to the Planner_Agent instead of HomepageNavigator
2. WHEN the Planner_Agent receives a homepage navigation task, THE Planner_Agent SHALL use MCP tools to analyze the page and identify careers navigation options
3. WHEN the Planner_Agent identifies a careers link, THE Planner_Agent SHALL instruct the Browser_Agent to click it using MCP tools
4. WHEN the navigation succeeds, THE Planner_Agent SHALL verify the destination page is a careers page using MCP tools to analyze page content
5. WHEN the navigation fails, THE Planner_Agent SHALL try alternative strategies (search, different links, etc.) using MCP tools
6. THE HomepageNavigator class SHALL remain available as a fallback for legacy mode when MCP is disabled

### Requirement 7: Graceful Fallback to Legacy Mode

**User Story:** As a system operator, I want the system to gracefully fall back to legacy automation when MCP is unavailable, so that the system remains functional even if MCP fails.

#### Acceptance Criteria

1. WHEN MCP connection fails during initialization, THE FSM_Orchestrator SHALL log the failure and continue with legacy automation mode
2. WHEN an MCP tool call fails during execution, THE Browser_Agent SHALL fall back to legacy DOM_Toolkit execution for that action
3. WHEN MCP is disabled in configuration, THE FSM_Orchestrator SHALL initialize agents without MCP_Client and use legacy mode
4. WHEN operating in legacy mode, THE Planner_Agent SHALL use the existing DOM state extraction and keyword matching strategies
5. WHEN operating in legacy mode, THE Browser_Agent SHALL use the existing DOM_Toolkit for browser interactions
6. FOR ALL fallback scenarios, THE system SHALL log the reason for using legacy mode for debugging purposes

### Requirement 8: MCP Tool Discovery and Validation

**User Story:** As a developer, I want the system to discover and validate available MCP tools at startup, so that I can verify the MCP server is functioning correctly.

#### Acceptance Criteria

1. WHEN the MCP_Client connects successfully, THE MCP_Client SHALL call the list_tools() method to discover available Playwright tools
2. WHEN tools are discovered, THE MCP_Client SHALL log the list of available tools for verification
3. WHEN the expected Playwright tools are not available, THE MCP_Client SHALL log a warning about missing tools
4. WHEN tool discovery fails, THE MCP_Client SHALL treat it as a connection failure and return False from connect()
5. THE MCP_Client SHALL validate that critical tools (playwright_navigate, playwright_click, playwright_fill) are available

### Requirement 9: MCP Error Handling and Retry Logic

**User Story:** As a system operator, I want robust error handling for MCP operations, so that transient failures don't cause the entire application workflow to fail.

#### Acceptance Criteria

1. WHEN an MCP tool call times out, THE Browser_Agent SHALL retry the operation up to the configured max_retries limit
2. WHEN an MCP tool call returns an error, THE Browser_Agent SHALL log the error details and attempt fallback to legacy mode
3. WHEN the MCP connection is lost during execution, THE Browser_Agent SHALL attempt to reconnect once before falling back to legacy mode
4. WHEN an MCP operation fails after all retries, THE Browser_Agent SHALL return a failure result with detailed error information
5. FOR ALL MCP errors, THE system SHALL log the error type, error message, and context for debugging

### Requirement 10: Configuration for MCP Integration

**User Story:** As a system administrator, I want to configure MCP integration behavior, so that I can control when and how MCP is used.

#### Acceptance Criteria

1. THE configuration file SHALL include an "mcp.enabled" boolean flag to enable/disable MCP integration
2. THE configuration file SHALL include "mcp.command" and "mcp.args" to specify how to launch the MCP server
3. THE configuration file SHALL include "mcp.timeout" to specify the timeout for MCP operations in milliseconds
4. THE configuration file SHALL include "mcp.fallback_to_legacy" boolean flag to control whether to fall back to legacy mode on MCP failures
5. WHEN "mcp.enabled" is false, THE FSM_Orchestrator SHALL skip MCP initialization and use legacy mode exclusively
6. WHEN "mcp.fallback_to_legacy" is false and MCP fails, THE system SHALL fail the operation rather than falling back to legacy mode

### Requirement 11: Logging and Observability for MCP Operations

**User Story:** As a developer, I want detailed logging of MCP operations, so that I can debug issues and understand system behavior.

#### Acceptance Criteria

1. WHEN an MCP tool is called, THE system SHALL log the tool name, arguments, and timestamp
2. WHEN an MCP tool returns a result, THE system SHALL log the result status, duration, and any error messages
3. WHEN the Planner_Agent makes a decision using MCP analysis, THE system SHALL log the decision rationale and supporting data
4. WHEN the system falls back to legacy mode, THE system SHALL log the reason and context for the fallback
5. WHEN MCP metrics are collected, THE system SHALL include MCP tool call counts, success rates, and latencies in the metrics report
6. THE StructuredLogger SHALL include MCP-specific log entries for analysis and debugging

### Requirement 12: Parser and Pretty Printer for MCP Responses

**User Story:** As a developer, I want to parse MCP JSON-RPC responses reliably and format them for logging, so that I can work with MCP data effectively.

#### Acceptance Criteria

1. THE MCP_Client SHALL parse JSON-RPC responses from the MCP server into structured Python objects
2. WHEN a JSON-RPC response contains an error, THE MCP_Client SHALL extract the error code and message
3. WHEN a JSON-RPC response contains a result, THE MCP_Client SHALL extract and return the result data
4. THE MCP_Client SHALL include a pretty_print_response() method that formats MCP responses for human-readable logging
5. WHEN parsing fails due to invalid JSON, THE MCP_Client SHALL log the raw response and return a parse error
6. FOR ALL MCP responses, parsing then pretty-printing then parsing SHALL produce an equivalent object (round-trip property)

