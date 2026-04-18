# 🛠️ Technical Guide: AI Auto-Apply & Orchestration

This guide provides a deep dive into the architecture, decision-making logic, and resilience patterns of the Job Scrapper's autonomous engine.

---

## 1. How the AI System Works

Think of the AI system as a **smart robot assistant** that applies to jobs for you. It:
1. **Reads** the job website using an optimized accessibility tree.
2. **Thinks** about the next step (e.g., "Should I click this button?" or "Fill this form?").
3. **Acts** by clicking, typing, and navigating using browser automation.
4. **Adapts** to diverse website structures without hardcoded selectors.

### The Application Loop
The system operates as a **Finite State Machine (FSM)**:
1. **NAVIGATE**: Moves to the career page URL.
2. **ANALYZE**: Generates a compact "Accessibility Tree" snapshot for the LLM.
3. **DECIDE**: The AI Planner determines the best action (Click, Fill, Scroll, Submit).
4. **EXECUTE**: The Browser Agent performs the action on the DOM.
5. **REPEAT**: Continues until the application is submitted or a terminal state is reached.

---

## 2. Token Optimization (Efficiency)

To maximize reliability on free AI tiers (like Ollama or Groq), the system implements aggressive token optimization:

### Smart HTML Extraction
*   **Targeted Context**: Instead of sending 50,000+ characters of raw HTML, we extract only `<nav>`, `<header>`, `<footer>`, and interactive elements.
*   **Result**: 80-95% reduction in token usage per request, allowing for 3-4x more job applications per day on free quotas.

### Accessibility Tree Snapshots
The agent uses Chrome DevTools Protocol (CDP) to generate a numbered list of interactive elements:
`[1] link "Search Jobs"`
`[2] button "Apply Now"`
This "AX-Tree" is 10x more token-efficient than raw DOM element lists.

---

## 3. Automatic Popup & Modal Handling

The system **automatically detects and closes** modals that block navigation (Cookie consents, newsletters, etc.).

### How it Works
The `_close_modal_popups()` method in `orchestrator.py` scans the page for 15+ common modal patterns including:
- **Cookies**: "Accept all", GDPR banners.
- **Newsletters**: "Subscribe for alerts".
- **Geo-Location**: "Switch to India site?".
- **Overlays**: Promotional banners or "Download our app" prompts.

### When It Runs
1. **Initial Load**: Immediately after arriving at a career page.
2. **Pre-Action**: Right before the AI attempts a critical click to prevent click-interception errors.

---

## 4. Frame Penetration (Piercing Iframes)
Enterprise systems like **Workday**, **Greenhouse**, and **Lever** often nest application forms inside `iframes`. 
Our `DOMToolkit` (in `dom_tools.py`) iterates through all frames on the page to ensure the AI "sees" inside the nested forms that traditional scrapers miss.

---

## 5. Troubleshooting & Advanced Setup

### Ollama Connectivity
If you see "Failed to connect to Ollama":
1. Ensure Ollama is running (`ollama serve` or check system tray).
2. Verify the model is pulled: `ollama pull llama3`.
3. Check `config.yaml` to ensure `ollama_base_url` is correct (default: `http://localhost:11434`).

### Slow Responses
Local AI inference depends on your hardware. If responses are slow:
- Close memory-intensive applications.
- Use a smaller model like `llama3:8b` or `phi3` in your config.
