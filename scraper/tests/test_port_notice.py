"""運航状況テキストからの港別情報の抽出（research R4）。"""

import pytest
from bs4 import BeautifulSoup

from scraper.db.models import Port
from scraper.utils.port_notice import extract_notice_text, extract_port_notices
from scraper.utils.ports import PortResolver
from tests.conftest import PORTS, read_fixture


@pytest.fixture
def resolver():
    return PortResolver(
        [Port(id=i, name=n, aliases=a) for i, (n, a, _) in enumerate(PORTS, start=1)]
    )


def _names(notices, resolver):
    by_id = {p.id: p.name for p in resolver.ports}
    return {by_id[n.port_id]: n for n in notices}


def test_normal_detail_page_has_no_notices(resolver):
    """平常時の詳細ページ（定型の注意書きを含む全文）では誤検出しない。"""
    html = read_fixture("marue/ship_detail_normal.html")
    text = extract_notice_text("通常運航致しております。", html)
    assert "台風の影響や" not in text
    assert "平土野" not in text
    assert extract_port_notices(text, resolver) == []


def test_normal_detail_full_text_has_no_notices(resolver):
    """念のため、注意書きまで含めたページ全文でも0件（仮定・案内の文を除外できている）。"""
    archive = BeautifulSoup(
        read_fixture("marue/ship_detail_normal.html"), "lxml"
    ).select_one("div.status-archive")
    full = "\n".join(p.get_text(" ", strip=True) for p in archive.find_all("p"))
    assert "港変更" in full and "抜港" in full
    assert extract_port_notices(full, resolver) == []


def test_body_is_taken_up_to_boilerplate():
    html = read_fixture("marue/ship_detail_normal.html").replace(
        "<p>通常運航致しております。</p>",
        "<p>気象荒天のため条件付運航。</p><p>与論港は抜港となります。</p>",
        1,
    )
    text = extract_notice_text("抜粋", html)
    assert text.splitlines() == [
        "抜粋",
        "気象荒天のため条件付運航。",
        "与論港は抜港となります。",
    ]


def test_excerpt_only_when_boilerplate_marker_missing():
    html = (
        "<div class='status-archive'><h4>見出し</h4><p>和泊港は条件付寄港。</p></div>"
    )
    assert extract_notice_text("抜粋", html) == "抜粋"
    assert extract_notice_text("抜粋", None) == "抜粋"


@pytest.mark.parametrize(
    "text", ["条件付寄港地: 和泊港、与論港", "和泊港・与論港は条件付寄港。"]
)
def test_conditional_ports(resolver, text):
    found = _names(extract_port_notices(text, resolver), resolver)
    assert set(found) == {"和泊", "与論"}
    assert all(n.kind == "conditional" for n in found.values())
    assert all(n.sentence for n in found.values())


def test_skip_port(resolver):
    found = _names(extract_port_notices("与論港は抜港", resolver), resolver)
    assert set(found) == {"与論"}
    assert found["与論"].kind == "skip"


def test_port_change(resolver):
    found = _names(
        extract_port_notices("亀徳港から平土野港へ港変更", resolver), resolver
    )
    assert set(found) == {"亀徳"}
    assert found["亀徳"].kind == "change"
    assert found["亀徳"].change_to == "平土野港"


def test_hypothetical_sentence_is_ignored(resolver):
    assert (
        extract_port_notices("港変更がある場合、亀徳港から平土野港になります", resolver)
        == []
    )
    assert extract_port_notices("与論港は抜港になる可能性があります。", resolver) == []


def test_skip_wins_over_conditional_for_same_port(resolver):
    found = _names(
        extract_port_notices("与論港は条件付寄港。与論港は抜港。", resolver), resolver
    )
    assert found["与論"].kind == "skip"


def test_mixed_kinds_in_one_sentence(resolver):
    found = _names(
        extract_port_notices("与論港は抜港、和泊港は条件付寄港", resolver), resolver
    )
    assert found["与論"].kind == "skip"
    assert found["和泊"].kind == "conditional"


def test_ports_not_on_route_only(resolver):
    assert extract_port_notices("茶花港は抜港", resolver) == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10月1日鹿児島新港発のフェリー波之上は与論港を抜港致します", {"与論": "skip"}),
        ("本日那覇港発の便は名瀬港から古仁屋港へ変更", {"名瀬": "change"}),
        ("那覇港向けの便は和泊港に条件付寄港します", {"和泊": "conditional"}),
        ("鹿児島行きの便は与論港は抜港", {"与論": "skip"}),
    ],
)
def test_voyage_description_ports_are_not_targets(resolver, text, expected):
    """「〇〇港発の便」のように便を説明しているだけの港には判定を付けない。"""
    found = _names(extract_port_notices(text, resolver), resolver)
    assert {name: n.kind for name, n in found.items()} == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "鹿児島新港を出港し、名瀬港・亀徳港に寄港後、与論港は抜港して那覇港へ向かいます。",
            {"与論": "skip"},
        ),
        ("与論港は抜港して那覇港へ向かいます", {"与論": "skip"}),
        (
            "和泊港、与論港は条件付寄港となります",
            {"和泊": "conditional", "与論": "conditional"},
        ),
        (
            "条件付寄港地: 和泊港、与論港、亀徳港",
            {"和泊": "conditional", "与論": "conditional", "亀徳": "conditional"},
        ),
        ("名瀬港に寄港後、和泊港は条件付寄港", {"和泊": "conditional"}),
        ("港変更：亀徳港から平土野港へ", {"亀徳": "change"}),
    ],
)
def test_only_ports_tied_to_keyword_are_targets(resolver, text, expected):
    """キーワードと結びついた港だけを対象にし、航路の説明に出てくるだけの港は判定しない。"""
    found = _names(extract_port_notices(text, resolver), resolver)
    assert {name: n.kind for name, n in found.items()} == expected
