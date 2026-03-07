import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session(
    retries: int = 3,
    backoff_factor: float = 1.0,
    timeout: int = 30,
) -> requests.Session:
    """Create a requests Session with retry logic and a Japanese browser UA."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    })

    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.request = lambda method, url, **kwargs: requests.Session.request(  # type: ignore[method-assign]
        session, method, url, timeout=kwargs.pop("timeout", timeout), **kwargs
    )

    return session
