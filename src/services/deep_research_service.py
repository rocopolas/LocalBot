import logging
import json
import asyncio
import os
import re
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime

from odf.opendocument import OpenDocumentText
from odf.style import Style, TextProperties, ParagraphProperties
from odf.text import P, H, List as OdfList, ListItem, Span
from odf.teletype import addTextToElement

from src.client import OllamaClient
from utils.search_utils import BraveSearch
from utils.config_loader import get_config
from src.constants import PROJECT_ROOT

logger = logging.getLogger(__name__)

class DeepResearchService:
    """Service for performing deep iterative research and generating reports."""
    
    def __init__(self):
        self.client = OllamaClient()
        self.model = get_config("MODEL")
        
    async def research(self, topic: str, chat_id: int, status_callback: Optional[Callable[[str], Any]] = None) -> str:
        """
        Performs deep research on a topic and returns the path to the generated ODT report.
        
        Args:
            topic: The research topic
            chat_id: The chat ID of the user requesting research
            status_callback: Async function to send status updates to the user
            
        Returns:
            Path to the generated ODT file
        """
        max_iterations = 5
        accumulated_knowledge = ""
        
        if status_callback:
            await status_callback(f"🧠 Starting research on: {topic}")
            
        for i in range(max_iterations):
            logger.info(f"Research iteration {i+1}/{max_iterations} for chat {chat_id}")
            
            # 1. Decide next action
            action_prompt = self._create_action_prompt(topic, accumulated_knowledge)
            response_json = await self._get_llm_json_response(action_prompt)
            
            if not response_json:
                logger.warning("Failed to get valid JSON from LLM. Aborting research loop.")
                break
                
            thought = response_json.get("thought", "No thought provided.")
            action = response_json.get("action", "finish")
            query = response_json.get("query", "")
            
            logger.info(f"Iteration {i+1}: Action={action}, Query={query}")
            
            if action == "finish":
                if status_callback:
                    await status_callback("✅ Information gathering complete. Generating report...")
                break
                
            if action == "search" and query:
                if status_callback:
                    await status_callback(f"🔍 Searching: {query}...")
                
                search_results = await BraveSearch.search(query, count=3)
                
                # Summarize findings to avoid context bloat
                summary = await self._summarize_results(topic, query, search_results)
                accumulated_knowledge += f"\n\n### Findings from '{query}':\n{summary}"
            else:
                logger.warning(f"Invalid action or missing query: {response_json}")
                break
        
        # 2. Generate Final Report
        if not accumulated_knowledge:
            accumulated_knowledge = "No specific information found, but I will write a report based on my internal knowledge."
            
        report_markdown = await self._generate_report_markdown(topic, accumulated_knowledge)
        
        # 3. Create ODT
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Sanitize topic for filename
        safe_topic = re.sub(r'[^\w\-]', '_', topic)
        # Limit length to avoid filesystem issues
        safe_topic = safe_topic[:50]
        
        filename = f"report_{safe_topic}_{timestamp}.odt"
        file_path = os.path.join(PROJECT_ROOT, "data", filename)
        
        # Ensure data directory exists
        os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
        
        self._create_odt(topic, report_markdown, file_path)
        
        return file_path

    def _create_action_prompt(self, topic: str, knowledge: str) -> str:
        return f"""You are a Deep Research Agent.
Topic: {topic}

Accumulated Knowledge:
{knowledge if knowledge else "(None yet)"}

Decide what to do next.
- If you need more information, search for it.
- If you have enough information to write a comprehensive report, finish.

Respond ONLY with a valid JSON object in this format:
{{
  "thought": "Reasoning for the decision",
  "action": "search" or "finish",
  "query": "The search query (required if action is search)"
}}
"""

    async def _get_llm_json_response(self, prompt: str) -> Optional[Dict]:
        """Get a JSON response from the LLM."""
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        
        async for chunk in self.client.stream_chat(self.model, messages):
            full_response += chunk
            
        # Try to clean up the response (remove markdown code blocks if any)
        full_response = full_response.strip()
        if full_response.startswith("```json"):
            full_response = full_response[7:]
        if full_response.startswith("```"):
            full_response = full_response[3:]
        if full_response.endswith("```"):
            full_response = full_response[:-3]
        
        full_response = full_response.strip()
        
        try:
            return json.loads(full_response)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON: {full_response}")
            return None

    async def _summarize_results(self, topic: str, query: str, results: str) -> str:
        """Summarize raw search results relevant to the topic."""
        prompt = f"""Topic: {topic}
Search Query: {query}
Raw Results:
{results}

Summarize the key findings from these results that are relevant to the topic. Be concise."""
        
        messages = [{"role": "user", "content": prompt}]
        summary = ""
        async for chunk in self.client.stream_chat(self.model, messages):
            summary += chunk
        return summary

    async def _generate_report_markdown(self, topic: str, knowledge: str) -> str:
        """Generate the final report in Markdown."""
        prompt = f"""Write a comprehensive research report on the following topic.
Topic: {topic}

Use the gathered information below:
{knowledge}

Format the report in Markdown.
- Use # for Title
- Use ## for Sections
- Use - for bullet points
- Be professional and detailed.
"""
        messages = [{"role": "user", "content": prompt}]
        report = ""
        async for chunk in self.client.stream_chat(self.model, messages):
            report += chunk
        return report

    def _create_odt(self, title: str, markdown_content: str, file_path: str):
        """Convert Markdown content to an ODT file."""
        textdoc = OpenDocumentText()
        
        # Styles
        s_header1 = Style(name="Heading 1", family="paragraph")
        s_header1.addElement(TextProperties(fontsize="24pt", fontweight="bold"))
        textdoc.styles.addElement(s_header1)
        
        s_header2 = Style(name="Heading 2", family="paragraph")
        s_header2.addElement(TextProperties(fontsize="18pt", fontweight="bold"))
        textdoc.styles.addElement(s_header2)
        
        s_text = Style(name="Standard", family="paragraph")
        s_text.addElement(TextProperties(fontsize="12pt"))
        textdoc.styles.addElement(s_text)
        
        # Bold Style
        s_bold = Style(name="Bold", family="text")
        s_bold.addElement(TextProperties(fontweight="bold"))
        textdoc.styles.addElement(s_bold)
        
        # Process content line by line (simple markdown parser)
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
                # Headers are already bold by style, so remove markdown bold markers
                clean_text = line[2:].replace("**", "").strip()
                h = H(outlinelevel=1, stylename=s_header1, text=clean_text)
                textdoc.text.addElement(h)
            elif line.startswith("## "):
                clean_text = line[3:].replace("**", "").strip()
                h = H(outlinelevel=2, stylename=s_header2, text=clean_text)
                textdoc.text.addElement(h)
            elif line.startswith("### "):
                 clean_text = line[4:].replace("**", "").strip()
                 h = H(outlinelevel=3, stylename=s_header2, text=clean_text)
                 textdoc.text.addElement(h)
            elif line.startswith("- ") or line.startswith("* "):
                # List handling with bold support
                p = P(stylename=s_text)
                # Add bullet manually as we are using paragraphs for lists (simple approach)
                addTextToElement(p, "• ")
                add_styled_text(p, line[2:])
                textdoc.text.addElement(p)
            else:
                p = P(stylename=s_text)
                add_styled_text(p, line)
                textdoc.text.addElement(p)
                
        textdoc.save(file_path)
