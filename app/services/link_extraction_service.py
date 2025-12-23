"""
Link Extraction Service

Extracts clickable links (URLs) from email content for easy access to verification/registration links.
"""
import re
from typing import List, Tuple, Optional
from html.parser import HTMLParser
from urllib.parse import urlparse


class LinkHTMLParser(HTMLParser):
    """HTML parser to extract links from HTML content"""

    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            # Extract href attribute
            href = None
            for attr_name, attr_value in attrs:
                if attr_name == "href":
                    href = attr_value
                    break
            if href:
                self.current_link = href
                self.current_text = []

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link:
            # Join collected text and store the link
            text = "".join(self.current_text).strip()
            self.links.append((self.current_link, text))
            self.current_link = None
            self.current_text = []

    def handle_data(self, data):
        if self.current_link:
            self.current_text.append(data)


class LinkExtractionService:
    """Service for extracting clickable links from email content"""

    # Comprehensive URL regex pattern - more permissive to capture full URLs
    URL_PATTERN = re.compile(
        r"https?://"  # http:// or https://
        r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)*"  # subdomains
        r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"  # domain
        r"(?:\.[A-Z]{2,6})+"  # TLD
        r"(?::\d+)?"  # optional port
        r"(?:/[^\s]*)?",  # path, query, fragment
        re.IGNORECASE,
    )

    def extract_from_text(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract URLs from plain text content
        
        Returns list of tuples: (url, context_text)
        """
        if not text:
            return []

        links = []
        seen_urls = set()

        # Find all URLs in the text
        for match in self.URL_PATTERN.finditer(text):
            url = match.group(0)
            
            # Strip trailing punctuation (.,!?;:) that's commonly at end of sentences
            url = url.rstrip('.,!?;:')
            
            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract context around the URL (40 chars before and after)
            start_pos = max(0, match.start() - 40)
            end_pos = min(len(text), match.end() + 40)
            context = text[start_pos:end_pos].strip()

            # Clean up context
            context = " ".join(context.split())
            if len(context) > 100:
                context = context[:97] + "..."

            links.append((url, context))

        return links

    def extract_from_html(self, html_content: str) -> List[Tuple[str, str]]:
        """
        Extract URLs from HTML content using proper HTML parsing
        
        Returns list of tuples: (url, link_text)
        """
        if not html_content:
            return []

        parser = LinkHTMLParser()
        try:
            parser.feed(html_content)
        except Exception as e:
            # If HTML parsing fails, fall back to text extraction
            print(f"[LinkExtractionService] HTML parsing error: {e}")
            return self.extract_from_text(html_content)

        # Filter and deduplicate links
        seen_urls = set()
        filtered_links = []

        for url, text in parser.links:
            # Skip empty or invalid URLs
            if not url or url.startswith("#") or url.startswith("javascript:"):
                continue

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Use URL as text if no text was provided
            if not text:
                text = url

            # Limit text length
            if len(text) > 100:
                text = text[:97] + "..."

            filtered_links.append((url, text))

        return filtered_links

    def extract_links(
        self, content: str, html_content: Optional[str] = None
    ) -> List[dict]:
        """
        Extract links from email content
        
        Args:
            content: Plain text content
            html_content: Optional HTML content (preferred if available)
        
        Returns:
            List of link dictionaries with url, text, and type
        """
        links = []

        # Prefer HTML extraction if available
        if html_content:
            extracted = self.extract_from_html(html_content)
            link_type = "html"
        else:
            extracted = self.extract_from_text(content)
            link_type = "text"

        # Convert to dictionary format
        for url, text in extracted:
            # Validate URL
            try:
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    continue
            except Exception:
                continue

            links.append(
                {
                    "url": url,
                    "text": text,
                    "type": link_type,
                    "domain": self._extract_domain(url),
                }
            )

        return links

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""

    def is_verification_link(self, url: str, text: str = "") -> bool:
        """
        Heuristic to determine if a link is likely a verification/activation link
        
        Returns True if the link contains common verification keywords
        """
        url_lower = url.lower()
        text_lower = text.lower()

        verification_keywords = [
            "verify",
            "confirm",
            "activate",
            "validation",
            "authentication",
            "signup",
            "register",
            "account",
            "token",
            "reset",
            "password",
        ]

        combined = url_lower + " " + text_lower

        return any(keyword in combined for keyword in verification_keywords)


# Singleton instance
link_extraction_service = LinkExtractionService()
