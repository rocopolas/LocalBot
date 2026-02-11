import os
import httpx
from dotenv import load_dotenv

load_dotenv()
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

class BraveSearch:
    """Utility class for Brave Search API."""
    
    BASE_URL = "https://api.search.brave.com/res/v1/web/search"
    
    @staticmethod
    async def search(query: str, count: int = 3) -> str:
        """
        Searches the web using Brave Search API.
        Returns formatted results as a string.
        """
        if not BRAVE_API_KEY:
            return "[Error: BRAVE_API_KEY not configured in .env]"
        
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_API_KEY
        }
        
        params = {
            "q": query,
            "count": count
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    BraveSearch.BASE_URL,
                    headers=headers,
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                # Format results
                results = []
                web_results = data.get("web", {}).get("results", [])
                
                for i, result in enumerate(web_results[:count], 1):
                    title = result.get("title", "No title")
                    description = result.get("description", "No description")
                    url = result.get("url", "")
                    results.append(f"{i}. **{title}**\n   {description}\n   {url}")
                
                if not results:
                    return "[No results found]"
                
                return "\n\n".join(results)
                
        except httpx.HTTPStatusError as e:
            return f"[Search error: {e.response.status_code}]"
        except Exception as e:
            return f"[Search error: {str(e)}]"

    @staticmethod
    async def search_images(query: str, count: int = 5) -> list[str]:
        """
        Searches for images using Brave Search API.
        Returns a list of image URLs.
        """
        if not BRAVE_API_KEY:
            return []
        
        url = "https://api.search.brave.com/res/v1/images/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": BRAVE_API_KEY
        }
        params = {"q": query, "count": count}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("results", [])
                image_urls = []
                for result in results:
                    # 'properties' -> 'url' is the image source
                    img_url = result.get("properties", {}).get("url")
                    if img_url:
                        image_urls.append(img_url)
                        
                return image_urls[:count]
                
        except Exception as e:
            print(f"[Brave Images] Error: {e}")
            return []
