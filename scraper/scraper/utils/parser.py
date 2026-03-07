from bs4 import BeautifulSoup, Tag


def get_text(element: Tag | None, strip: bool = True) -> str:
    """Safely extract text from a BeautifulSoup element."""
    if element is None:
        return ""
    return element.get_text(strip=strip)


def parse_html(html: str, parser: str = "lxml") -> BeautifulSoup:
    return BeautifulSoup(html, parser)
