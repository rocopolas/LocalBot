import logging
import os
import re
from typing import Optional, Callable, Any
from datetime import datetime

from odf.opendocument import OpenDocumentText
from odf.style import Style, TextProperties
from odf.text import P, H, Span
from odf.teletype import addTextToElement

from src.client import OllamaClient
from utils.config_loader import get_config
from src.constants import DATA_DIR
from src.services.deep_research.orchestrator import DeepResearchOrchestrator
from src.services.deep_research.writer import Writer

logger = logging.getLogger(__name__)


class DeepResearchService:
    """
    Service for performing deep iterative research and generating reports.
    
    Uses a 5-module architecture:
    1. Planner - Decomposes questions into sub-tasks
    2. Hunter - Searches for sources
    3. Reader - Extracts relevant content
    4. Critic - Evaluates quality and controls loop
    5. Writer - Synthesizes final report
    """
    
    def __init__(self):
        self.client = OllamaClient()
        self.model = get_config("MODEL")
        self.max_iterations = 15  # Maximum research iterations
        self.search_count = 5     # Sources per search
        
    async def research(
        self, 
        topic: str, 
        chat_id: int, 
        status_callback: Optional[Callable[[str], Any]] = None
    ) -> str:
        """
        Performs deep research on a topic and returns the path to the generated ODT report.
        
        Args:
            topic: The research topic/question
            chat_id: The chat ID of the user requesting research
            status_callback: Async function to send status updates to the user
            
        Returns:
            Path to the generated ODT file
        """
        logger.info(f"Starting Deep Research V2 for chat {chat_id}: {topic[:50]}...")
        
        try:
            # Detect language
            language = await self._detect_language(topic)
            logger.info(f"Detected language for deep research: {language}")

            # Create orchestrator
            orchestrator = DeepResearchOrchestrator(
                llm_client=self.client,
                model=self.model,
                max_iterations=self.max_iterations,
                search_count=self.search_count,
                status_callback=status_callback,
                concurrent_tasks=2  # Process 2 tasks at once for speed
            )
            
            # Execute research workflow
            context = await orchestrator.execute_research(topic, chat_id, language)
            
            # Generate report using Writer module
            writer = Writer(self.client)
            report_markdown = await writer.write_report(context, self.model)
            
            # Create ODT file
            file_path = self._create_odt_report(topic, report_markdown)
            
            # Send completion notification
            if status_callback:
                total_chunks = len(context.get_all_completed_chunks())
                total_sources = len(set(
                    c.source.url for c in context.get_all_completed_chunks()
                ))
                await status_callback(
                    f"✅ Research complete!\n"
                    f"📊 {total_chunks} chunks from {total_sources} sources\n"
                    f"🔄 {context.iteration_count} iterations\n"
                    f"📝 Generating report..."
                )
            
            logger.info(f"Deep Research V2 completed for chat {chat_id}")
            return file_path
            
        except Exception as e:
            logger.error(f"Error in Deep Research V2: {e}", exc_info=True)
            if status_callback:
                await status_callback(f"❌ Error during research: {str(e)}")
            raise
    
    def _create_odt_report(self, title: str, markdown_content: str) -> str:
        """
        Convert Markdown report to ODT file.
        
        Args:
            title: Report title/topic
            markdown_content: Markdown formatted report
            
        Returns:
            Path to generated ODT file
        """
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r'[^\w\-]', '_', title)[:50]
        filename = f"report_{safe_topic}_{timestamp}.odt"
        file_path = os.path.join(DATA_DIR, filename)
        
        # Ensure data directory exists
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Create ODT document
        textdoc = OpenDocumentText()
        
        # Define styles
        s_header1 = Style(name="Heading 1", family="paragraph")
        s_header1.addElement(TextProperties(fontsize="24pt", fontweight="bold"))
        textdoc.styles.addElement(s_header1)
        
        s_header2 = Style(name="Heading 2", family="paragraph")
        s_header2.addElement(TextProperties(fontsize="18pt", fontweight="bold"))
        textdoc.styles.addElement(s_header2)
        
        s_text = Style(name="Standard", family="paragraph")
        s_text.addElement(TextProperties(fontsize="12pt"))
        textdoc.styles.addElement(s_text)
        
        s_bold = Style(name="Bold", family="text")
        s_bold.addElement(TextProperties(fontweight="bold"))
        textdoc.styles.addElement(s_bold)
        
        # Process content
        lines = markdown_content.split('\n')
        
        def add_styled_text(parent_element, text):
            """Helper to parse **bold** and add to element"""
            parts = re.split(r'(\*\*.*?\*\*)', text)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    s = Span(stylename=s_bold)
                    addTextToElement(s, part[2:-2])
                    parent_element.addElement(s)
                else:
                    addTextToElement(parent_element, part)
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith("# "):
                # H1
                clean_text = line[2:].replace("**", "").strip()
                h = H(outlinelevel=1, stylename=s_header1, text=clean_text)
                textdoc.text.addElement(h)
            elif line.startswith("## "):
                # H2
                clean_text = line[3:].replace("**", "").strip()
                h = H(outlinelevel=2, stylename=s_header2, text=clean_text)
                textdoc.text.addElement(h)
            elif line.startswith("### "):
                # H3
                clean_text = line[4:].replace("**", "").strip()
                h = H(outlinelevel=3, stylename=s_header2, text=clean_text)
                textdoc.text.addElement(h)
            elif line.startswith("- ") or line.startswith("* "):
                # Bullet list
                p = P(stylename=s_text)
                addTextToElement(p, "• ")
                add_styled_text(p, line[2:])
                textdoc.text.addElement(p)
            elif re.match(r'^\[\d+\]', line):
                # Citation reference [1], [2], etc.
                p = P(stylename=s_text)
                add_styled_text(p, line)
                textdoc.text.addElement(p)
            else:
                # Regular paragraph
                p = P(stylename=s_text)
                add_styled_text(p, line)
                textdoc.text.addElement(p)
        
        # Save document
        textdoc.save(file_path)
        logger.info(f"ODT report saved to: {file_path}")
        
        return file_path

    async def _detect_language(self, text: str) -> str:
        """
        Detect the language of the text using LLM.
        Defaults to 'English' if uncertain.
        """
        try:
            prompt = f"""Analyze the following text and determine its language.
Text: "{text}"

Respond ONLY with the language name in English (e.g., "English", "Spanish", "French").
If uncertain, respond with "English".
"""
            messages = [{"role": "user", "content": prompt}]
            language = ""
            async for chunk in self.client.stream_chat(self.model, messages):
                language += chunk
            
            return language.strip()
        except Exception as e:
            logger.error(f"Error detecting language: {e}")
            return "English"
