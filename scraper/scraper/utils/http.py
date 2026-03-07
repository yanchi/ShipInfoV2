import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session(
    retries: int = 3,
    backoff_factor: float = 1.0,
    retry_post: bool = False,
) -> requests.Session:
    """Create a requests Session with retry logic and a Japanese browser UA.

    Args:
        retries: Maximum number of retry attempts.
        backoff_factor: Backoff multiplier between retries.
        retry_post: If True, POST requests are also retried on 429/5xx.
            Only enable this when POST requests are known to be idempotent
            (no side effects), otherwise duplicate submissions may occur.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    })

    allowed_methods = ["GET", "HEAD"]
    if retry_post:
        allowed_methods.append("POST")

    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=allowed_methods,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session
