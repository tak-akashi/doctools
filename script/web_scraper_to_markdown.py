"""
Multi-Site Web Scraper with Markdown Conversion

Requirements:
pip install selenium beautifulsoup4 html2text webdriver-manager lxml

Usage:
python scraper.py
"""

import os
import re
import time
from typing import List, Tuple, Optional, Union, Dict
from urllib.parse import urlparse, urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import html2text


class WebScraper:
    def __init__(self, headless: bool = True, wait_time: int = 10) -> None:
        """
        Initialize the web scraper
        
        Args:
            headless (bool): Run browser in headless mode
            wait_time (int): Maximum wait time for page loads
        """
        self.wait_time = wait_time
        self.setup_driver(headless)
        self.setup_html2text()
        
    def setup_driver(self, headless: bool) -> None:
        """Setup Chrome WebDriver with options"""
        options = Options()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, self.wait_time)
        
    def setup_html2text(self) -> None:
        """Setup html2text converter with custom settings"""
        self.h = html2text.HTML2Text()
        self.h.ignore_links = False
        self.h.ignore_images = False
        self.h.body_width = 0  # No line wrapping
        self.h.unicode_snob = True
        self.h.skip_internal_links = False
        self.h.ignore_tables = False  # Keep tables as HTML
        
    def get_content_selector(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Determine the content selector based on URL pattern
        
        Args:
            url (str): The URL to analyze
            
        Returns:
            tuple: (selector_type, selector_value) or (None, None) for general scraping
        """
        url_patterns = {
            'https://help.line.me/': ('class', 'LyContents'),
            'https://guide.line.me/': ('class', 'contentWrap'),
            'https://linestep.jp/': ('id', 'main-wrap'),
            'https://appllio.com/': ('class', 'main-content')
        }
        
        for pattern, (selector_type, selector_value) in url_patterns.items():
            if url.startswith(pattern):
                return selector_type, selector_value
                
        return None, None
    
    def remove_unwanted_elements(self, soup: BeautifulSoup) -> BeautifulSoup:
        """
        Remove navigation, sidebar, and other unwanted elements for general sites
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object to clean
        """
        # Common selectors for elements to remove
        unwanted_selectors = [
            'nav', 'navbar', 'navigation',
            'sidebar', 'side-bar', 'aside',
            'header', 'footer',
            'menu', 'menubar', 'menu-bar',
            'breadcrumb', 'breadcrumbs',
            'advertisement', 'ads', 'ad',
            'social', 'share', 'sharing',
            'comment', 'comments',
            'popup', 'modal',
            'newsletter', 'subscription'
        ]
        
        # Remove by tag names
        for tag in ['nav', 'aside', 'header', 'footer']:
            for element in soup.find_all(tag):
                element.decompose()
        
        # Remove by class and id patterns
        for selector in unwanted_selectors:
            # Remove by class
            for element in soup.find_all(class_=re.compile(selector, re.I)):
                element.decompose()
            # Remove by id
            for element in soup.find_all(id=re.compile(selector, re.I)):
                element.decompose()
        
        # Remove script and style tags
        for element in soup.find_all(['script', 'style', 'noscript']):
            element.decompose()
            
        return soup
    
    def extract_content(self, url: str) -> Optional[BeautifulSoup]:
        """
        Extract content from a webpage
        
        Args:
            url (str): The URL to scrape
            
        Returns:
            BeautifulSoup: The extracted content as BeautifulSoup object
        """
        try:
            print(f"Accessing: {url}")
            self.driver.get(url)
            
            # Wait for page to load
            time.sleep(3)
            
            # Get page source
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'lxml')
            
            # Determine extraction method based on URL
            selector_type, selector_value = self.get_content_selector(url)
            
            if selector_type and selector_value:
                # Extract specific content for known sites
                if selector_type == 'class':
                    content = soup.find('div', class_=selector_value)
                elif selector_type == 'id':
                    content = soup.find('div', id=selector_value)
                
                if content:
                    print(f"Found specific content selector: {selector_type}='{selector_value}'")
                    return content
                else:
                    print(f"Specific selector not found, falling back to general extraction")
            
            # General content extraction
            # Try to find main content area
            main_content = None
            content_selectors = [
                ('tag', 'main'),
                ('class', 'content'),
                ('class', 'main-content'),
                ('class', 'post-content'),
                ('class', 'entry-content'),
                ('id', 'content'),
                ('id', 'main'),
                ('class', 'article'),
                ('tag', 'article')
            ]
            
            for selector_type, selector_value in content_selectors:
                if selector_type == 'tag':
                    main_content = soup.find(selector_value)
                elif selector_type == 'class':
                    main_content = soup.find(class_=re.compile(selector_value, re.I))
                elif selector_type == 'id':
                    main_content = soup.find(id=re.compile(selector_value, re.I))
                
                if main_content:
                    print(f"Found main content using: {selector_type}='{selector_value}'")
                    break
            
            if not main_content:
                # If no main content found, use body but remove unwanted elements
                main_content = soup.find('body')
                if main_content:
                    main_content = self.remove_unwanted_elements(main_content)
                    print("Using body content after removing unwanted elements")
            
            return main_content if main_content else soup
            
        except Exception as e:
            print(f"Error extracting content from {url}: {str(e)}")
            return None
    
    def process_tables(self, soup: BeautifulSoup) -> BeautifulSoup:
        """
        Process tables to maintain HTML format in markdown
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object containing tables
        """
        if soup:
            # Find all tables and mark them to preserve HTML
            for table in soup.find_all('table'):
                # Add a marker that html2text will preserve
                table['data-preserve-html'] = 'true'
        return soup
    
    def convert_to_markdown(self, soup: BeautifulSoup, base_url: str) -> str:
        """
        Convert BeautifulSoup content to markdown
        
        Args:
            soup (BeautifulSoup): The content to convert
            base_url (str): Base URL for resolving relative links
            
        Returns:
            str: Markdown content
        """
        if not soup:
            return ""
        
        # Process tables to preserve HTML format
        soup = self.process_tables(soup)
        
        # Convert relative URLs to absolute URLs
        for link in soup.find_all('a', href=True):
            link['href'] = urljoin(base_url, link['href'])
        
        for img in soup.find_all('img', src=True):
            img['src'] = urljoin(base_url, img['src'])
        
        # Convert to markdown
        html_content = str(soup)
        markdown = self.h.handle(html_content)
        
        # Post-process to preserve table HTML
        # This is a simple approach - you might need to enhance it
        lines = markdown.split('\n')
        processed_lines = []
        in_table = False
        
        for line in lines:
            if '<table' in line:
                in_table = True
            elif '</table>' in line:
                in_table = False
                processed_lines.append(line)
                continue
            
            if in_table and line.strip():
                # Preserve table HTML lines
                processed_lines.append(line)
            elif not in_table:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def scrape_url(self, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Scrape a single URL and convert to markdown
        
        Args:
            url (str): The URL to scrape
            
        Returns:
            tuple: (success, markdown_content, error_message)
        """
        try:
            content_soup = self.extract_content(url)
            if content_soup:
                markdown = self.convert_to_markdown(content_soup, url)
                return True, markdown, None
            else:
                return False, None, "Failed to extract content"
        except Exception as e:
            return False, None, str(e)
    
    def scrape_multiple_urls(
        self,
        urls: List[str],
        output_dir: str = "output/scraped_content",
    ) -> List[Tuple[str, bool, Optional[str], Optional[str]]]:
        """
        Scrape multiple URLs and save as markdown files
        
        Args:
            urls (list): List of URLs to scrape
            output_dir (str): Directory to save markdown files
        """
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        results: List[Tuple[str, bool, Optional[str], Optional[str]]] = []
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Processing: {url}")
            
            success, markdown, error = self.scrape_url(url)
            
            if success:
                # Generate filename from URL
                parsed_url = urlparse(url)
                filename = f"{parsed_url.netloc}_{parsed_url.path.replace('/', '_')}.md"
                filename = re.sub(r'[^\w\-_.]', '_', filename)
                if filename.endswith('_.md'):
                    filename = filename[:-4] + '.md'
                
                filepath = os.path.join(output_dir, filename)
                
                # Save markdown content
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {url}\n\n")
                    f.write(f"Scraped at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write("---\n\n")
                    f.write(markdown)
                
                print(f"✓ Saved to: {filepath}")
                results.append((url, True, filepath, None))
            else:
                print(f"✗ Failed: {error}")
                results.append((url, False, None, error))
        
        return results
    
    def close(self) -> None:
        """Close the webdriver"""
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def __enter__(self) -> 'WebScraper':
        return self
    
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[object]) -> None:
        self.close()


def main():
    """Main function to demonstrate usage"""
    # Example URLs to scrape
    urls = [
        "https://help.line.me/line/?lang=ja&contentId=20000098",
        "https://guide.line.me/ja/friends-and-groups/search-line-id.html",
        "https://linestep.jp/2025/06/07/lstep-application/",
        "https://appllio.com/line-message-sending-reservation"
    ]
    
    # Create scraper instance
    with WebScraper(headless=True) as scraper:
        print("Starting web scraping...")
        
        # Scrape multiple URLs
        results = scraper.scrape_multiple_urls(urls)
        
        # Print summary
        print("\n" + "="*50)
        print("SCRAPING SUMMARY")
        print("="*50)
        
        successful = 0
        failed = 0
        
        for url, success, filepath, error in results:
            if success:
                print(f"✓ {url} -> {filepath}")
                successful += 1
            else:
                print(f"✗ {url} -> Error: {error}")
                failed += 1
        
        print(f"\nTotal: {len(results)} | Successful: {successful} | Failed: {failed}")
        print(f"Output directory: scraped_content/")


if __name__ == "__main__":
    main()
