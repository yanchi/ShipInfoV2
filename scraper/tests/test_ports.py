"""PortResolver（港名の正規化）のテスト。"""
import pytest

from scraper.db.models import Port
from scraper.utils.ports import PortResolver

PORTS = [
    (1, "鹿児島", ["鹿児島新港", "鹿児島"]),
    (2, "名瀬", ["名瀬港", "名瀬"]),
    (3, "亀徳", ["亀徳新港", "亀徳港", "亀徳"]),
    (4, "和泊", ["和泊港", "和泊"]),
    (5, "与論", ["与論港", "与論"]),
    (6, "本部", ["本部港", "本部"]),
    (7, "那覇", ["那覇港", "那覇"]),
]


@pytest.fixture
def resolver():
    return PortResolver([Port(id=i, name=n, aliases=a) for i, n, a in PORTS])


@pytest.mark.parametrize(
    "text,expected",
    [
        ("鹿児島", "鹿児島"),
        ("鹿児島新港", "鹿児島"),
        ("名瀬港", "名瀬"),
        ("名瀬", "名瀬"),
        ("亀徳新港", "亀徳"),
        ("亀徳港", "亀徳"),
        ("亀徳", "亀徳"),
        ("和泊港", "和泊"),
        ("与論港", "与論"),
        ("本部港", "本部"),
        ("那覇港", "那覇"),
        ("奄美大島 名瀬港", "名瀬"),
    ],
)
def test_resolve_aliases(resolver, text, expected):
    port = resolver.resolve(text)
    assert port is not None and port.name == expected


def test_resolve_prefers_longest_alias(resolver):
    """「鹿児島新港」は「鹿児島」より先にマッチする（同じ港でも長い別名で取る）。"""
    assert resolver.resolve("鹿児島新港向け").name == "鹿児島"


def test_resolve_unknown_returns_none(resolver):
    assert resolver.resolve("平土野港") is None
    assert resolver.resolve("") is None
    assert resolver.resolve(None) is None


def test_find_all_in_order_without_duplicates(resolver):
    text = "和泊港・与論港は条件付寄港。和泊港は再確認。"
    assert [p.name for p in resolver.find_all(text)] == ["和泊", "与論"]


def test_find_all_does_not_double_count_overlapping_alias(resolver):
    text = "鹿児島新港から那覇港"
    assert [p.name for p in resolver.find_all(text)] == ["鹿児島", "那覇"]


def test_find_all_ignores_unknown_ports(resolver):
    assert [p.name for p in resolver.find_all("亀徳港から平土野港へ")] == ["亀徳"]
