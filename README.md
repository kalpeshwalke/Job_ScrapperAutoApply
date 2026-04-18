# Job_ScrapperAutoApply

AI-powered job scraping and autonomous application engine. Uses Playwright and DrissionPage for resilient automation across LinkedIn, Naukri, and Indeed. Features a robust FSM orchestrator with atomic save protection for high-fidelity job tracking and submission.

---

## 📚 Documentation Guide

**Core Documentation:**
- **README.md** (this file) - Project overview, installation, and Ollama setup.
- **TECHNICAL_GUIDE.md** - Deep dive into AI system architecture, token optimization, and automatic popup handling.

**Configuration:**
- **config/config.yaml** - All configuration options with inline comments.
- **.env.example** - Environment variables template.

---

## Core Capabilities

### High-Performance Scraping
- **Parallel Platform Execution**: Scrape all enabled job boards simultaneously for up to 70% reduction in execution time.
- **Intelligent Cross-Platform Deduplication**: Sophisticated composite hashing ensures you never see the same job twice, regardless of where it's posted.
- **Multi-Level Cache Layer**: Integrated SQLite backend caches job listings, reducing redundant network calls and bypassing platform limits on repeated runs.
- **Resilient Pipeline**: Per-platform timeouts and partial-save logic ensure you get results even when a specific platform is unreachable.

### Autonomous Application Engine
- **Local AI Sovereignty**: Powered by **Ollama** for 100% free, unlimited, and private job applications without third-party API keys, quotas, or rate limits.
- **Universal Workflow Logic**: Orchestrates a Finite State Machine (FSM) that adapts to diverse career page structures across the enterprise landscape.
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

### 4. Ollama Setup (Required for Auto-Apply)

**Install Ollama:**
1. Download from [ollama.com/download/windows](https://ollama.com/download/windows)
2. Run the installer
3. Pull the llama3 model: `ollama pull llama3`
4. Verify installation: `ollama list`

**Test Your Setup:**
```bash
python test_ollama_setup.py
```

This will verify:
- ✅ Ollama is running
- ✅ llama3 model is available
- ✅ JSON generation works
- ✅ Tool calling format is correct
- ✅ Config is properly set

**Why Ollama?**
- 🆓 **100% Free** - No API costs ever
- ♾️ **Unlimited Usage** - No rate limits or quotas
- 🔒 **Privacy** - All processing happens locally
- 🚀 **Fast** - 2-5 seconds per response
- 📴 **Offline** - Works without internet after model download

### 5. Running the System

**Graphical Mode (Windows)**:
Double-click `run_scraper.bat` in the root directory.

**Manual Launch**:
```bash
python main.py
```

**First Time Setup:**
1. Configure your profile in `config/config.yaml`.
2. Set up Ollama (see step 4 above).
3. Run `python tests/manual/test_ollama_setup.py` to verify.
4. Launch the scraper with `python main.py` or `run_scraper.bat`.

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
## Troubleshooting (Windows)
If you see errors related to emojis or characters in your terminal, use:
`python test_ollama_setup.py`
The script has been updated with an ASCII fallback mode to ensure compatibility with standard Windows Command Prompt and PowerShell.
