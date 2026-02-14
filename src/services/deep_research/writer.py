"""Writer module: Synthesizes research into final report."""
import logging
from datetime import datetime
from typing import List

from src.services.deep_research.models import Chunk, ResearchContext

logger = logging.getLogger(__name__)


class Writer:
    """Synthesizes all research chunks into a comprehensive report."""
    
    def __init__(self, llm_client):
        self.client = llm_client
    
    async def write_report(
        self, 
        context: ResearchContext, 
        model: str
    ) -> str:
        """
        Generate final research report in Markdown.
        
        Args:
            context: Complete research context with all chunks
            model: LLM model to use
            
        Returns:
            Markdown formatted report
        """
        logger.info(f"Writer synthesizing report with {len(context.chunks)} chunks")
        
        # Prepare chunks with citations
        chunks_with_citations = self._prepare_citations(context.chunks)
        
        # Generate report
        prompt = self._create_report_prompt(context, chunks_with_citations)
        
        try:
            messages = [{"role": "user", "content": prompt}]
            report = ""
            
            async for chunk in self.client.stream_chat(model, messages):
                report += chunk
            
            # Add citations section at the end
            citations_section = self._generate_citations_section(chunks_with_citations)
            full_report = report.strip() + "\n\n" + citations_section
            
            return full_report
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return self._generate_fallback_report(context)
    
    def _prepare_citations(self, chunks: List[Chunk]) -> List[dict]:
        """Prepare chunks with unique citation numbers."""
        seen_urls = {}
        citations = []
        citation_num = 1
        
        for chunk in chunks:
            url = chunk.source.url
            if url not in seen_urls:
                seen_urls[url] = citation_num
                citations.append({
                    "number": citation_num,
                    "chunk": chunk,
                    "source": chunk.source
                })
                citation_num += 1
            else:
                # Use existing citation number
                citations.append({
                    "number": seen_urls[url],
                    "chunk": chunk,
                    "source": chunk.source
                })
        
        return citations
    
    def _create_report_prompt(
        self, 
        context: ResearchContext, 
        citations: List[dict]
    ) -> str:
        """Create the report generation prompt."""
        # Build context text with citations
        context_text = "\n\n".join([
            f"[{c['number']}] {c['chunk'].content}\n(Source: {c['source'].title} - {c['source'].url})"
            for c in citations
        ])
        
        return f"""You are a Research Report Writer. Write a comprehensive research report based on the collected information.

Original Research Question: {context.original_question}

Research Data:
Total sources analyzed: {len(set(c['source'].url for c in citations))}
Total information chunks: {len(citations)}

Collected Information:
{context_text}

Write a professional research report that:
1. Has a clear, descriptive title
2. Includes an executive summary
3. Is organized into logical sections with proper headings
4. Synthesizes information from multiple sources
5. Uses inline citations [1], [2], etc. when referencing specific information
6. Maintains academic/professional tone
7. Includes a conclusion that answers the original question
8. IS WRITTEN IN {context.language.upper()}

IMPORTANT: The entire report MUST be written in {context.language}.

Format in Markdown:
- # for title
- ## for main sections
- ### for subsections
- - for bullet points
- **bold** for emphasis

Important: Use citations like [1], [2] throughout the text when making claims based on the research data.
"""
    
    def _generate_citations_section(self, citations: List[dict]) -> str:
        """Generate the references/citations section."""
        # Get unique citations
        seen = set()
        unique_citations = []
        
        for c in citations:
            if c['number'] not in seen:
                seen.add(c['number'])
                unique_citations.append(c)
        
        # Sort by citation number
        unique_citations.sort(key=lambda x: x['number'])
        
        lines = ["## References\n"]
        for c in unique_citations:
            lines.append(f"[{c['number']}] {c['source'].title} - {c['source'].url}")
        
        return "\n".join(lines)
    
    def _generate_fallback_report(self, context: ResearchContext) -> str:
        """Generate a simple fallback report if LLM fails."""
        lines = [
            f"# Research Report: {context.original_question}",
            "",
            "## Summary",
            f"This report is based on {len(context.chunks)} information chunks from {len(set(c.source.url for c in context.chunks))} unique sources.",
            "",
            "## Findings",
            ""
        ]
        
        for i, chunk in enumerate(context.chunks, 1):
            lines.append(f"### Finding {i}")
            lines.append(chunk.content)
            lines.append(f"\n*Source: [{chunk.source.title}]({chunk.source.url})*")
            lines.append("")
        
        return "\n".join(lines)
