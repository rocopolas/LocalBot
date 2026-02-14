"""Orchestrator: Coordinates the entire Deep Research workflow."""
import logging
from datetime import datetime
from typing import Optional, Callable, Any

from src.services.deep_research.models import (
    ResearchContext,
    ResearchTask,
    TaskStatus,
    IterationDecision
)
from src.services.deep_research.planner import Planner
from src.services.deep_research.hunter import Hunter
from src.services.deep_research.reader import Reader
from src.services.deep_research.critic import Critic
from src.services.deep_research.writer import Writer

logger = logging.getLogger(__name__)


class DeepResearchOrchestrator:
    """
    Orchestrates the complete Deep Research workflow:
    Planner → Hunter → Reader → Critic → (loop or Writer)
    """
    
    def __init__(
        self,
        llm_client,
        model: str,
        max_iterations: int = 15,
        search_count: int = 5,
        status_callback: Optional[Callable[[str], Any]] = None,
        concurrent_tasks: int = 2
    ):
        self.client = llm_client
        self.model = model
        self.max_iterations = max_iterations
        self.search_count = search_count
        self.status_callback = status_callback
        self.concurrent_tasks = concurrent_tasks
        
        # Initialize modules
        self.planner = Planner(llm_client)
        self.hunter = Hunter(search_count=search_count)
        self.reader = Reader(
            llm_client, 
            min_relevance=0.7,
            max_concurrent=5,  # Increased from default for speed
            fetch_delay=0.5    # Reduced delay
        )
        self.critic = Critic(llm_client, min_chunks_per_task=2)
        self.writer = Writer(llm_client)
    
    async def execute_research(
        self, 
        question: str, 
        chat_id: int,
        language: str = "English"
    ) -> ResearchContext:
        """
        Execute the complete research workflow.
        
        Args:
            question: Original research question
            chat_id: Telegram chat ID
            language: Target language for the report
            
        Returns:
            ResearchContext with all collected data
        """
        await self._notify(f"🧠 Starting Deep Research on: {question}")
        
        # Initialize context
        context = ResearchContext(
            original_question=question,
            max_iterations=self.max_iterations,
            language=language
        )
        
        # PHASE 1: PLANNING
        await self._notify("📋 Phase 1: Planning research tasks...")
        tasks = await self.planner.create_research_plan(question, self.model)
        context.tasks = tasks
        
        await self._notify(f"📋 Created {len(tasks)} research tasks")
        logger.info(f"Planner created {len(tasks)} tasks for chat {chat_id}")
        
        # PHASE 2: EXECUTE RESEARCH LOOP
        await self._notify(f"🔍 Phase 2: Executing research loop (max {self.max_iterations} iterations)...")
        
        while context.iteration_count < self.max_iterations:
            pending_tasks = context.get_pending_tasks()
            
            if not pending_tasks:
                await self._notify(f"✅ All tasks completed after {context.iteration_count} iterations!")
                break
            
            # Determine how many tasks to process concurrently
            # Limit by:
            # 1. Configured concurrency
            # 2. Available pending tasks
            # 3. Remaining iterations allowed
            remaining_iterations = self.max_iterations - context.iteration_count
            batch_size = min(self.concurrent_tasks, len(pending_tasks), remaining_iterations)
            
            batch = pending_tasks[:batch_size]
            
            await self._notify(f"🚀 Processing batch of {len(batch)} tasks concurrently...")
            
            # Create coroutines for the batch
            coroutines = []
            for task in batch:
                context.iteration_count += 1
                coroutines.append(self._process_task(task, context, context.iteration_count))
            
            # Execute batch
            import asyncio
            await asyncio.gather(*coroutines)
            
            # Notify iteration progress
            await self._notify(f"📊 Progress: {context.iteration_count}/{self.max_iterations} iterations completed")
            
            # Check if we should continue or have enough information
            if context.iteration_count >= self.max_iterations:
                await self._notify(f"⏱️ Reached maximum iterations ({self.max_iterations})")
                break
        
        # PHASE 3: FINAL EVALUATION (if needed)
        if context.iteration_count >= self.max_iterations:
            await self._notify("🔍 Phase 3: Final evaluation...")
            should_continue, additional_tasks = await self.critic.evaluate_final(context, self.model)
            
            if should_continue and additional_tasks:
                await self._notify(f"⚠️ Adding {len(additional_tasks)} emergency tasks...")
                context.tasks.extend(additional_tasks)
                
                # Process emergency tasks
                for task in additional_tasks:
                    if context.iteration_count < self.max_iterations:
                        context.iteration_count += 1
                        await self._process_task(task, context, context.iteration_count)
        
        # PHASE 4: WRITING
        await self._notify("📝 Phase 4: Synthesizing report...")
        
        total_chunks = len(context.get_all_completed_chunks())
        await self._notify(f"📊 Synthesizing {total_chunks} information chunks into report...")
        
        return context
    
    async def _process_task(self, task: ResearchTask, context: ResearchContext, iteration_number: int):
        """Process a single research task through the full pipeline."""
        await self._notify(f"🔍 Iteration {iteration_number}/{self.max_iterations}: {task.query[:50]}...")
        task.status = TaskStatus.IN_PROGRESS
        
        # Step 1: Hunt for sources
        await self._notify(f"  → Searching web...")
        sources = await self.hunter.hunt(task)
        
        if not sources:
            await self._notify(f"  ⚠️ No sources found for: {task.query[:40]}...")
            task.status = TaskStatus.FAILED
            return
        
        task.sources_found = sources
        await self._notify(f"  ✓ Found {len(sources)} sources")
        
        # Step 2: Read and extract chunks
        await self._notify(f"  → Reading sources...")
        chunks = await self.reader.read_sources(sources, task.query, self.model)
        
        if not chunks:
            await self._notify(f"  ⚠️ No relevant content extracted")
            task.status = TaskStatus.FAILED
            return
        
        task.chunks_extracted = chunks
        context.chunks.extend(chunks)
        await self._notify(f"  ✓ Extracted {len(chunks)} relevant chunks")
        
        # Step 3: Critic evaluation
        await self._notify(f"  → Evaluating quality...")
        decision, gap = await self.critic.evaluate_task(task, chunks, context, self.model)
        
        if decision == IterationDecision.FINISH:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            await self._notify(f"  ✓ Task complete - sufficient information")
        else:
            # Gap found - create new tasks from gap analysis
            if gap and gap.suggested_queries:
                await self._notify(f"  🔄 Gaps found - adding {len(gap.suggested_queries)} follow-up tasks")
                import uuid
                
                for query in gap.suggested_queries:
                    new_task = ResearchTask(
                        id=str(uuid.uuid4())[:8],
                        query=query,
                        priority=task.priority + 1,
                        status=TaskStatus.PENDING,
                        parent_task_id=task.id
                    )
                    context.tasks.append(new_task)
            
            task.status = TaskStatus.COMPLETED  # Mark as completed but added children
            task.completed_at = datetime.now()
    
    async def _notify(self, message: str):
        """Send status notification if callback is configured."""
        if self.status_callback:
            try:
                await self.status_callback(message)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")
        
        logger.info(message)
