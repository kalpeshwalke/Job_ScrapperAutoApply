import os
import sys
import time
import logging
import asyncio
from unittest.mock import MagicMock, patch

# Add src to path if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ai_auto_apply.core.orchestrator import FSMOrchestrator
from src.common.config import Config
from src.common.logger import setup_logger

logger = logging.getLogger(__name__)

async def run_visual_test():
    """
    Runs a visual dry-run of the auto-apply engine on a real career page.
    SAFETY BRAKES are engaged to prevent final submission.
    """
    setup_logger()
    logger.info("Starting Visual Dry-Run Test")
    
    # 1. Initialize Orchestrator
    orchestrator = FSMOrchestrator()
    
    # 2. Define Test Job (Anthropic)
    job_data = {
        "title": "Research Engineer / Research Scientist, Vision",
        "company": "Anthropic",
        "url": "https://boards.greenhouse.io/anthropic/jobs/5074217008",
        "location": "San Francisco, CA"
    }
    
    # 3. Patch Planner to prevent submission (Safety Brakes)
    from src.ai_auto_apply.agents.planner_agent import PlannerAgent
    
    original_plan = PlannerAgent.plan_next_step
    
    def patched_plan(self, dom_state, job_data, context):
        plan = original_plan(self, dom_state, job_data, context)
        # If AI wants to submit, we stop and mark as failed (dry run success)
        if plan and plan.get("status") == "in_progress" and "submit" in plan.get("next_step", "").lower():
            logger.info("======================================================================")
            logger.info("SAFETY BRAKES ENGAGED: AI intends to submit the form.")
            logger.info("======================================================================")
            logger.info("Look at the browser... All fields should be filled!")
            logger.info("Holding for 15 seconds so you can inspect the screen...")
            time.sleep(15)
            
            # Return a special failure state to stop the orchestrator
            return {
                "status": "failed",
                "next_step": "DRY RUN COMPLETE: Paused before final submission.",
                "reasoning": "Safety brakes engaged for dry run verification."
            }
        return plan
    
    with patch.object(PlannerAgent, 'plan_next_step', patched_plan):
        logger.info(f"Processing job: {job_data['title']} at {job_data['company']}")
        result = await orchestrator.apply_to_job(job_data)
        
        if result.get("status") == "failed" and "DRY RUN COMPLETE" in result.get("reason", ""):
            logger.info("[OK] Visual Dry-Run Successful! Safety brakes worked.")
        else:
            logger.info(f"[FAIL] Result status: {result.get('status')}. Reason: {result.get('reason')}")

if __name__ == "__main__":
    asyncio.run(run_visual_test())
