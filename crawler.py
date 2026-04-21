import logging
from firecrawl import Firecrawl
from config import FIRECRAWL_API_KEY

logger = logging.getLogger(__name__)

try:
    fire_app = Firecrawl(api_key=FIRECRAWL_API_KEY)
except Exception as e:
    logger.error(f"Firecrawl initialization error: {e}")
    fire_app = None

async def deep_crawl_url(url, limit=5):
    """Crawl a URL and discover internal links using the v1 SDK logic."""
    if not fire_app:
        raise Exception("Firecrawl is not initialized. Check your FIRECRAWL_API_KEY.")
    
    try:
        result = fire_app.crawl(
            url=url,
            limit=limit,
            scrape_options={
                'formats': ['markdown'],
                'onlyMainContent': True
            }
        )
        
        if not result or 'data' not in result:
            logger.warning(f"Crawl returned no data for {url}")
            return []
        
        return result.get('data', [])
        
    except Exception as e:
        logger.error(f"Crawl failed for {url}: {e}")
        raise Exception(f"Firecrawl API error: {str(e)[:100]}")