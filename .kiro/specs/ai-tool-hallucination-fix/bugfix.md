# Bugfix Requirements Document

## Introduction

The AI auto-apply system is failing to complete job applications due to the AI model (qwen2.5:3b) hallucinating non-existent tool names instead of using the actual available tools defined in `_get_tool_definitions()`. During testing with Gururo company, the AI invented tools like `apply_for_job`, `custom_search_engine`, and `generate_job_ad_template` instead of using the six actual tools (`click_element`, `enter_text`, `select_option`, `upload_file`, `press_key`, `navigate`). This results in the system getting stuck in decision loops (7+ iterations with no progress) and failing to submit any job applications, rendering the core functionality completely broken.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the AI model receives a step to execute THEN the system invents non-existent tool names like `apply_for_job`, `custom_search_engine`, `generate_job_ad_template`, `apply_job_description`, `custom_interview_preparation_tool`, and `search_interview_questions`

1.2 WHEN the AI model hallucinates a tool name THEN the system attempts to execute the non-existent tool without validation, resulting in execution failure

1.3 WHEN the AI model fails to use correct tools THEN the system enters a decision loop repeating the same failed strategies across 7+ iterations without progress

1.4 WHEN the AI model receives the DOM state and job details THEN the system does not use the actual available tools (`click_element`, `enter_text`, `select_option`, `upload_file`, `press_key`, `navigate`) to interact with the page

1.5 WHEN the system prompt is provided to the AI model THEN the AI model ignores the tool definitions and invents its own tool names

1.6 WHEN the AI model makes incorrect tool decisions THEN the system takes 20-25 seconds per iteration without completing the job application

### Expected Behavior (Correct)

2.1 WHEN the AI model receives a step to execute THEN the system SHALL only use tool names from the defined list: `click_element`, `enter_text`, `select_option`, `upload_file`, `press_key`, `navigate`

2.2 WHEN the AI model attempts to use a tool name THEN the system SHALL validate the tool name against the allowed list before execution and reject any hallucinated tool names

2.3 WHEN the AI model uses an invalid tool name THEN the system SHALL provide clear error feedback to the AI with the list of valid tools and request a retry with correct tool names

2.4 WHEN the AI model receives the DOM state and job details THEN the system SHALL successfully use the available tools to interact with page elements and complete the job application

2.5 WHEN the system prompt is provided to the AI model THEN the system SHALL explicitly list all available tools at the beginning of the prompt with clear warnings against inventing tool names

2.6 WHEN the AI model makes tool decisions THEN the system SHALL complete job applications end-to-end without getting stuck in decision loops

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the AI model correctly uses valid tool names (`click_element`, `enter_text`, `select_option`, `upload_file`, `press_key`, `navigate`) THEN the system SHALL CONTINUE TO execute those tools successfully

3.2 WHEN the system navigates to a careers page THEN the system SHALL CONTINUE TO successfully detect and navigate from homepage to careers page

3.3 WHEN the system analyzes DOM state THEN the system SHALL CONTINUE TO correctly parse and prioritize interactive elements with mmid attributes

3.4 WHEN the system integrates with Ollama THEN the system SHALL CONTINUE TO successfully connect to the Ollama API at `http://localhost:11434` and receive AI responses

3.5 WHEN the system logs interactions THEN the system SHALL CONTINUE TO capture and log all AI decisions, tool calls, and execution results

3.6 WHEN the system uses MCP or legacy execution modes THEN the system SHALL CONTINUE TO support both execution paths with proper fallback logic
