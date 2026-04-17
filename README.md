# Job_ScrapperAutoApply

AI-powered job scraping and autonomous application engine. Uses Playwright and DrissionPage for resilient automation across LinkedIn, Naukri, and Indeed. Features a robust FSM orchestrator with atomic save protection for high-fidelity job tracking and submission.

---

## Core Capabilities

### High-Performance Scraping
- **Parallel Platform Execution**: Scrape all enabled job boards simultaneously for up to 70% reduction in execution time.
- **Intelligent Cross-Platform Deduplication**: Sophisticated composite hashing ensures you never see the same job twice, regardless of where it's posted.
- **Multi-Level Cache Layer**: Integrated SQLite backend caches job listings, reducing redundant network calls and bypassing platform limits on repeated runs.
- **Resilient Pipeline**: Per-platform timeouts and partial-save logic ensure you get results even when a specific platform is unreachable.

### Autonomous Application Engine
- **Universal Workflow Logic**: Orchestrates a Finite State Machine (FSM) that adapts to diverse career page structures across the enterprise landscape.
- **Multi-Backend Support**: Seamlessly switch between logic engines including DeepSeek, Gemini, and local Ollama instances.
- **Career Page Integrity**: Automated validation ensures career page URLs are active and correctly mapped before tracking begins.
- **Anti-Spam Intelligence**: Atomic Excel-based tracking ensures that each job is only ever processed once by the engine.
- **Visual Feedback Loop**: Optional screenshot capture and detailed DOM interaction logging provide total visibility into the application process.

---

## Technical Excellence

### Atomic Save Pattern
To prevent data corruption during high-frequency job tracking, the system implements an **Atomic Save Pattern**. Data is first written to a temporary buffer and only replaces the master tracking file upon successful verification of the write operation.

### Resilience & Resource Management
The orchestrator is built with comprehensive `try...finally` resource protection. Whether the script completes successfully or is interrupted by the user (Ctrl+C), all browser instances and network resources are guaranteed to be released.

---

## Getting Started

### 1. Prerequisites
- Python 3.11 or higher
- Chrome Browser (latest version recommended)

### 2. Basic Installation
```bash
# Clone the repository
git clone https://github.com/kalpeshwalke/Job_ScrapperAutoApply.git
cd Job_ScrapperAutoApply

# Install dependencies
pip install -r requirements.txt
```

### 3. Core Configuration
Edit `config/config.yaml` to set your preferences:
```yaml
profile:
  role: "QA Engineer"
  experience_years: 3
  skills: ["Playwright", "Selenium", "API Testing"]
```

### 4. Running the System
**Graphical Mode (Windows)**:
Double-click `job_run_scraper.bat` to launch the interactive CLI menu.

**Manual Launch**:
```bash
python main.py
```

---

## System Architecture

### Orchestration Layer
The system operates as a unified entry point (`main.py`) that delegates to specialized managers:
- **ScraperManager**: Manages the lifecycle and parallelization of platform-specific scrapers.
- **AutonomousOrchestrator**: Executes the FSM logic for high-fidelity application workflows.

---

## Security & Ethics
- **Stealth Preservation**: The system implements human-mimicry delays and persistent profile management to respect platform integrity.
- **Privacy First**: All credentials (passwords, API keys) are managed exclusively through a local `.env` file and are never committed to the repository.
- **Data Ownership**: Scraped listings and application history are stored locally in Excel and SQLite formats.

## License
Distributed under the **MIT License**. See `LICENSE` for more information.

---

*Professionally engineered for stable, efficient, and ethical automated job hunting.*
