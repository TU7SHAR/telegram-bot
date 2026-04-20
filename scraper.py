import os
import io
import tempfile
import asyncio
import requests
import xml.etree.ElementTree as ET
from markitdown import MarkItDown
from firecrawl import Firecrawl
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from config import FIRECRAWL_API_KEY

md_converter = MarkItDown()
MAX_WORDS = 3000

def init_firecrawl():
    """Initialize Firecrawl with API key from config"""
    if not FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY is missing.")
    return Firecrawl(api_key=FIRECRAWL_API_KEY)

def clean_and_truncate(text):
    """Truncate text to MAX_WORDS if needed"""
    words = text.split()
    if len(words) > MAX_WORDS:
        return " ".join(words[:MAX_WORDS]), True
    return text, False

async def extract_content(file_bytes, filename):
    """Extract content from uploaded files using MarkItDown converter"""
    fd, tmp_path = tempfile.mkstemp(suffix=f"_{filename}")
    try:
        with os.fdopen(fd, 'wb') as tmp:
            tmp.write(file_bytes)
        result = await asyncio.to_thread(md_converter.convert, tmp_path)
        content, is_truncated = clean_and_truncate(result.text_content)
        return content, is_truncated
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def create_downloadable_buffer(content, filename):
    """Convert string content to downloadable byte buffer"""
    buffer = io.BytesIO(content.encode('utf-8'))
    buffer.name = filename
    return buffer

def scrape_single_url(url):
    """
    Scrapes a single URL using Firecrawl.
    Returns markdown content extracted from the webpage.
    """
    try:
        app = init_firecrawl()
        
        # Call scrape with URL and markdown format
        result = app.scrape(url, formats=['markdown'])
        
        # result is a Document object - access attributes with dot notation
        if hasattr(result, 'markdown') and result.markdown:
            # Get title from metadata if available
            title = 'Scraped Page'
            if hasattr(result, 'metadata') and result.metadata:
                if hasattr(result.metadata, 'title') and result.metadata.title:
                    title = result.metadata.title
            
            # Clean and truncate the content
            content, truncated = clean_and_truncate(result.markdown)
            
            return {
                "success": True,
                "title": title,
                "content": content,
                "truncated": truncated
            }
        else:
            return {"success": False, "error": "No markdown content found"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

def extract_sitemap_urls(sitemap_url, max_urls=10):
    """
    Fetches and parses sitemap.xml file.
    Extracts list of URLs and filters out media files.
    """
    BAD_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.pdf', '.mp4', '.zip')

    def _fetch_urls(url, visited, current_list):
        if url in visited or len(current_list) >= max_urls:
            return
        
        visited.add(url)
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                return
            
            root = ET.fromstring(resp.content)
            
            for elem in root.iter():
                if len(current_list) >= max_urls:
                    break
                    
                if 'loc' in elem.tag and elem.text:
                    loc = elem.text.strip()
                    clean_loc = loc.split('?')[0].lower()
                    
                    if clean_loc.endswith('.xml'):
                        # Found another sitemap - process it too
                        _fetch_urls(loc, visited, current_list)
                    elif not clean_loc.endswith(BAD_EXTENSIONS) and loc not in current_list:
                        current_list.append(loc)
                        
        except Exception as e:
            pass

    try:
        final_urls = []
        _fetch_urls(sitemap_url, set(), final_urls)
        return {"success": True, "urls": final_urls}
    except Exception as e:
        return {"success": False, "error": str(e)}

def crawl_website_links(start_url, max_pages=10):
    """
    Crawls a website by finding internal links in HTML.
    Automatically discovers and visits all internal pages.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    visited = set()
    queue = [start_url]
    found_urls = []
    domain = urlparse(start_url).netloc

    while queue and len(found_urls) < max_pages:
        current_url = queue.pop(0)
        
        if current_url in visited:
            continue
            
        visited.add(current_url)
        found_urls.append(current_url)
        
        try:
            response = requests.get(current_url, headers=headers, timeout=5)
            
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                full_url = urljoin(current_url, link['href']).split('?')[0]
                
                # Only follow internal links from same domain
                if (urlparse(full_url).netloc == domain and 
                    full_url not in visited and 
                    full_url not in queue and
                    not full_url.lower().endswith(('.pdf', '.jpg', '.png', '.xml', '.zip', '.css', '.js'))):
                    queue.append(full_url)
                    
        except Exception as e:
            continue

    return {"success": True, "urls": found_urls}