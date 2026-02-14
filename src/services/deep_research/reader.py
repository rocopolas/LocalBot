"""Reader module: Extracts relevant content from sources."""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from src.services.deep_research.models import Source, Chunk
from utils.web_fetcher import WebFetcher

logger = logging.getLogger(__name__)


class Reader:
    """Reads and extracts relevant content chunks from web sources."""
    
    def __init__(
        self,
        llm_client,
        min_relevance: float = 0.7,
        max_concurrent: int = 3,
        fetch_delay: float = 1.0
    ):
        self.client = llm_client
        self.min_relevance = min_relevance
        self.fetcher = WebFetcher()
        self.max_concurrent = max_concurrent
        self.fetch_delay = fetch_delay
    
    async def read_sources(
        self, 
        sources: List[Source], 
        task_query: str, 
        model: str
    ) -> List[Chunk]:
        """
        Extract relevant content chunks from sources.
        Uses rate-limited concurrent fetching with delay between requests.
        
        Args:
            sources: List of sources to read
            task_query: The original task query for relevance checking
            model: LLM model to use
            
        Returns:
            List of Chunk objects with relevant content
        """
        chunks = []
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_source(source: Source) -> List[Chunk]:
            """Process a single source with rate limiting."""
            async with semaphore:
                try:
                    # Fetch full content using WebFetcher (trafilatura)
                    content = await self._fetch_content(source.url)
                    
                    if not content or len(content.strip()) < 50:
                        # Use description as fallback
                        logger.warning(f"Using description fallback for {source.url}")
                        content = source.description
                    
                    source.fetched_content = content
                    source.fetched_at = datetime.now()
                    
                    # Extract relevant chunks using LLM
                    extracted_chunks = await self._extract_relevant_chunks(
                        content=content,
                        source=source,
                        task_query=task_query,
                        model=model
                    )
                    
                    # Add delay between requests to be polite
                    await asyncio.sleep(self.fetch_delay)
                    
                    return extracted_chunks
                    
                except Exception as e:
                    logger.error(f"Error reading source {source.url}: {e}")
                    # Create chunk from description as fallback
                    return [Chunk(
                        content=source.description,
                        source=source,
                        relevance_score=0.5,
                        extracted_at=datetime.now(),
                        task_id=source.task_id
                    )]
        
        # Process all sources concurrently with rate limiting
        tasks = [process_source(source) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all chunks
        for result in results:
            if isinstance(result, list):
                chunks.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Source processing failed: {result}")
        
        logger.info(f"Reader extracted {len(chunks)} chunks from {len(sources)} sources")
        return chunks
    
    async def _fetch_content(self, url: str) -> str:
        """
        Fetch content from URL using WebFetcher (trafilatura).
        
        Args:
            url: The URL to fetch
            
        Returns:
            Extracted main content text or empty string if failed
        """
        try:
            content = await self.fetcher.fetch_content(url)
            return content if content else ""
        except Exception as e:
            logger.error(f"Error fetching content from {url}: {e}")
            return ""
    
    async def _extract_relevant_chunks(
        self, 
        content: str, 
        source: Source,
        task_query: str,
        model: str
    ) -> List[Chunk]:
        """Use LLM to extract relevant chunks from content."""
        prompt = self._create_extraction_prompt(content, source, task_query)
        
        try:
            response = await self._get_llm_response(prompt, model)
            chunks_data = self._parse_extraction_response(response)
            
            chunks = []
            for chunk_data in chunks_data:
                # Validate chunk data
                if not isinstance(chunk_data, dict) or "content" not in chunk_data:
                    continue
                    
                relevance = chunk_data.get("relevance", 0.5)
                
                # Only keep highly relevant chunks
                if relevance >= self.min_relevance:
                    chunk = Chunk(
                        content=chunk_data["content"],
                        source=source,
                        relevance_score=relevance,
                        extracted_at=datetime.now(),
                        task_id=source.task_id
                    )
                    chunks.append(chunk)
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error extracting chunks: {e}")
            # Return entire content as single chunk
            return [Chunk(
                content=content[:2000],  # Limit content length
                source=source,
                relevance_score=0.5,
                extracted_at=datetime.now(),
                task_id=source.task_id
            )]
    
    def _create_extraction_prompt(self, content: str, source: Source, task_query: str) -> str:
        """Create prompt for chunk extraction."""
        return f"""You are a Content Extraction Agent. Your task is to extract relevant information from web content.

Task Query: {task_query}
Source Title: {source.title}
Source URL: {source.url}

Content to analyze:
---
{content[:8000] if len(content) > 8000 else content}
---

Extract the most relevant information chunks that answer the task query.
Each chunk should be a complete, self-contained piece of information.

Respond ONLY with a valid JSON array in this format:
[
  {{
    "content": "The extracted text chunk with relevant information",
    "relevance": 0.95
  }},
  {{
    "content": "Another relevant chunk",
    "relevance": 0.85
  }}
]

Guidelines:
- Relevance score: 0.0 to 1.0 (1.0 = highly relevant)
- Extract only substantial information, not fluff
- Each chunk should be 1-3 sentences or a short paragraph
- Maximum 5 chunks per source
- If content is not relevant, return empty array []
"""
    
    async def _get_llm_response(self, prompt: str, model: str) -> str:
        """Get response from LLM."""
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        
        async for chunk in self.client.stream_chat(model, messages):
            full_response += chunk
        
        return full_response.strip()
    
    def _parse_extraction_response(self, response: str) -> List[dict]:
        """Parse JSON response from LLM."""
        # Clean up response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        try:
            data = json.loads(response)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "chunks" in data:
                return data["chunks"]
            else:
                return []
        except json.JSONDecodeError:
            logger.error(f"Failed to parse extraction response: {response[:200]}")
            return []
