# Research: スクレイパーを振る舞いを変えずに整理する

2026-11-02 時点の master（`8bcd99c`）を読んで決めた。行番号はその時点の `scraper/scraper/scrapers/marue_ferry.py`。

## R1: 両社の共通処理をどこに置くか（US1・FR-004）

**Decision**: `_load_routes()` と `_load_stops()` を `BaseScraper`（`scraper/scraper/scrapers/base.py`）に移し、両社の同じ名前のメソッドを消す。

- 両社の `_load_routes()` は1文字も違わない（始発港「鹿児島」が下り・「那覇」が上り、`active` の航路だけ）
- `_load_stops()` もクエリと戻り値が同じ。違いはマリックスの docstring だけ（それを残す）
- マルエーの `_get_stops()`（キャッシュつき）・`_get_resolver()`・`_load_port_codes()`・`_marix_company_id()` はマルエーだけが使うので動かさない

**Rationale**: どちらも `self.session` と `self.company_id` だけを使い、`BaseScraper` が持っている。両社が同じ名前で呼んでいるので、呼び出し側は1行も変わらない。

**Alternatives considered**:
- `utils/` に関数で置く（`load_routes(session, company_id)`）：呼び出し側を全部書き換えることになり、差分が増える。`BaseScraper` に置けばメソッドのまま。却下
- 始発港の名前をクラス属性にして会社ごとに変えられるようにする：今の2社は同じで、3社目の形はまだ分からない。使わない口を作らない（spec US3 の「無理な抽象化をしない」と同じ）。却下

## R2: マルエーフェリーをどう分けるか（US2・FR-005）

**Decision**: `marue_ferry.py` を **パッケージ `marue_ferry/`** にし、役割ごとの **mixin** に分ける。`MarueFerry` は mixin を組み合わせたクラスとして `marue_ferry/__init__.py` に置く。

```
scraper/scraper/scrapers/marue_ferry/
├── __init__.py    # MarueFerry（mixin を組む）・外から使う名前の再エクスポート・全体の説明
├── common.py      # URL・定数・dataclass（SearchRow ほか）・正規表現・モジュール関数（_nearest_date ほか）
├── state.py       # MarueState(BaseScraper)：__init__・インスタンス変数の宣言・マルエーだけの読み込み
├── fetch.py       # FetchMixin：fetch()・便検索のキー・_search()・raw_html_hash の材料
├── ships.py       # ShipsMixin：一覧・船の詳細の読み取り（_parse_ships・_classify・_parse_voyages ほか）
├── voyages.py     # VoyagesMixin：便の特定・突き合わせ（_match_voyage・_current_voyage_status ほか）
├── extra.py       # ExtraMixin：臨時便（_parse_extra_voyages・_build_extra_voyage・_extra_records・抜港のフラグ・取り下げの削除）
└── statuses.py    # StatusesMixin：parse()（航路単位）・parse_departures()（港別）・_upsert_departures()
```

メソッドの置き場所（行番号は今のファイル）：

| ファイル | 中身 | 今の行 | 目安の行数 |
|---|---|---|---|
| `__init__.py` | モジュールの説明（各ファイルへの案内）、`class MarueFerry(StatusesMixin, ExtraMixin, VoyagesMixin, ShipsMixin, FetchMixin)`、`__all__` | 1–101・215 | 〜80 |
| `common.py` | `SEARCH_URL`〜`_CONDITIONAL_WORDS`、dataclass 7つ、`_VOYAGE_LINE`〜`_WEEKDAYS`、`_nearest_date`・`_parse_search_datetime`・`_iso` | 103–214・1742–1788 | 〜170 |
| `state.py` | `__init__`、インスタンス変数の型注釈、`_get_resolver`・`_get_stops`・`_load_port_codes`・`_marix_company_id`・`_route_directions` | 216–219・1427–1434・1661–1670・1704–1720 | 〜110 |
| `fetch.py` | `fetch`〜`_search`（`_format_search_date` を含む） | 225–495 | 〜290 |
| `ships.py` | `_require_ship_statuses`・`_ship_detail_text`・`_parse_ships`・`_classify`・`_parse_voyages`・`_is_from_midway`・`_parse_status_text` | 578–590・1439–1539・1721–1741 | 〜170 |
| `voyages.py` | `_skipped_record`〜`_recorded_voyage`（`_ship_notices`・`_for_current_voyage` を含む） | 990–1426 | 〜460 |
| `extra.py` | `_extra_records`〜`_note_extra_conflict`（`_upsert_departures` を除く）、`_parse_extra_voyages`・`_build_extra_voyage` | 718–821・828–989・1540–1660 | 〜400 |
| `statuses.py` | `parse`・`_route_status`・`_worst_ship_status`・`parse_departures`・`_upsert_departures` | 500–577・595–713・822–827 | 〜220 |

- モジュールの docstring（今の 1–101 行）は、段落ごとにその役割のファイルの docstring に移す（「処理の流れ・検索結果・raw_html_hash」→ `fetch.py`、「航路単位・港別」→ `statuses.py`、「港別情報・便の照合」→ `voyages.py`、「臨時便」→ `extra.py`）。文は変えない。`__init__.py` には全体の流れと、どこに何があるかだけを書く
- mixin はどれも `MarueState` を継承する。エディタで `self.session`・`self._log`・`self._ships` などが解決でき、`StatusesMixin._upsert_departures()` の `super()` が `BaseScraper` に届く
- ほかの mixin のメソッドを呼ぶところ（`ExtraMixin` から `_match_voyage()` など）は今のまま `self.` で呼ぶ。MRO で解決される

**Rationale**:
- 今のコードは、`fetch()` で作った `self._ships`・`self._searches`・`self._extra_voyages` などを `parse_departures()` と臨時便の処理が読む、状態を共有した1つのクラス。mixin なら **メソッドの中身を1行も変えずに** ファイルだけ分けられる（FR-001・FR-008）
- テストは `scraper._search`・`scraper._parse_ships`・`scraper._extra_skips_after` など中のメソッドを直接呼んでいる（48 か所以上）。メソッドが `MarueFerry` のインスタンスから同じ名前で呼べれば、テストの呼び出しは変わらない（FR-002）
- パッケージにすると、`from scraper.scrapers.marue_ferry import MarueFerry, SEARCH_URL, ...` が今のまま使える（FR-003）

**Alternatives considered**:
- 役割ごとのクラスに分けて、`MarueFerry` から呼ぶ（委譲）：共有している状態（`_ships`・`_searches`・`_voyage_cache`・`_recorded_cache`・`_extra_voyages`・`_parse_now`・`_notices`・`_current_voyage` ほか）を引数か共通のオブジェクトで渡すことになり、メソッドの中身をほぼ全部書き換える。テストの `scraper._search(...)` も全部変わる。振る舞いを変えない整理としてはリスクが大きすぎる。却下（状態を減らす作り直しは、必要になったら別の機能で）
- モジュール関数に分ける：同じ理由（状態を引数で渡す）で却下
- `marue_ferry.py` を残して、隣に `marue_ferry_extra.py` などを足す：`scrapers/` に会社の名前のファイルが散らばり、どれが登録されたスクレイパーか分かりにくい。却下

## R3: テストの差し替え先（FR-002・Edge Cases）

**Decision**: `tests/test_marue_ferry.py` の差し替え先だけを直す。期待値・入力・テストの数は変えない。

| 今 | 後 |
|---|---|
| `fixed_now()`：`patch("scraper.scrapers.marue_ferry.date")`・`...datetime` | 時計を読むサブモジュール（`fetch`・`ships`・`voyages`・`extra`・`statuses`）ごとに `date`・`datetime` を差し替える。`base` の `datetime` はそのまま |
| `no_sleep()`：`patch("scraper.scrapers.marue_ferry.time.sleep")` | `patch("scraper.scrapers.marue_ferry.fetch.time.sleep")` |
| `monkeypatch.setattr("scraper.scrapers.marue_ferry.settings.marue_search_days_ahead", 1)` | `"scraper.scrapers.marue_ferry.extra.settings.marue_search_days_ahead"`（`settings` は1つのオブジェクトなので、どの場所からでも同じものを変える） |
| `from scraper.scrapers.marue_ferry import KAGOSHIMA_URL, SEARCH_URL, ExtraStop, ExtraVoyage, MarueFerry` | 変えない（`__init__.py` が再エクスポート） |

- 時計を読むメソッド（今の行）：`fetch`（226・235）→ `fetch.py`、`parse`（506・520）・`parse_departures`（601）→ `statuses.py`、`_extra_records`（724）・`_delete_withdrawn_extra_rows`（836–837）・`_build_extra_voyage`（1602）→ `extra.py`、`_current_voyage_status`（1152）・`_voyage_departed`（1367・1380）→ `voyages.py`、`_parse_voyages`（1490）→ `ships.py`
- `fixed_now()` は、サブモジュールの一覧を1か所（タプル）に持ってループで `patch` する。差し替え忘れたモジュールがあると、その日のテストが本当の今日で動いて落ちるので、漏れはテストで分かる
- `test_marix_line.py`・`test_base_*.py` は変えない（マリックスはファイルを分けず、`base` の `datetime` の場所も変わらない）

**Rationale**: `patch()` は「その名前を読むモジュールの属性」を差し替える。`date.today()` を呼ぶコードが別のファイルに移れば、差し替える場所も移すしかない（spec Assumptions で許した範囲）。

**Alternatives considered**:
- 時計を1つの関数（`common.today()`・`common.now()`）にまとめ、テストはそこだけ差し替える：メソッドの中身を変えることになる（FR-008 の「整理だけ」から外れる）。テストを楽にするためのコードの変更は、この機能ではやらない。却下
- `__init__.py` で `date`・`datetime`・`time` を import して、今の patch 先を残す：パッケージの属性を差し替えても、サブモジュールが読む名前は変わらないので効かない。却下

## R4: 「DB に書く内容が変わらない」の確かめ方（FR-001・SC-002）

**Decision**: pytest のプラグイン [snapshot_plugin.py](snapshot_plugin.py) で、DB を使うテスト（270 件）ごとに終わったときの全テーブルの行を JSON Lines に書き出し、[compare_snapshots.py](compare_snapshots.py) で整理の前後を比べる。手順は [quickstart.md](quickstart.md)。

- 書き出すのは `pytest_runtest_teardown`（フィクスチャの後片付けより先）。テーブルは `Base.metadata` から取る（`:memory:` の SQLite は接続が1つなので、`inspect()` で別の接続を開くとトランザクションがぶつかる）
- 書かない列：`id`（挿入順で決まる代理キー）と実行時刻の列（`created_at`・`updated_at`・`scraped_at`・`checked_at`・`started_at`・`finished_at`）。行は中身で並べ替える
- 整理の前に2回流し、2回で違ったセル（`datetime.now()` から時刻を作るテストの `scheduled_departure_at`・`content_hash` など）は比べない。`PYTHONHASHSEED=0` で流す
- 確認済み（2026-11-02、変更前のコードで3回）：270 テスト・比べないセル 95・違い 0
- プラグインはリポジトリのテストに入れない（テストの数を変えない。FR-002）。`specs/17-scraper-refactor/` に置き、コンテナの `/tmp` にコピーして使う

**Rationale**: 既存のテストは個々の値を確かめているが、確かめていない列（`status_detail` の文・`content_hash`・`source_url` など）の変化は見逃す。全部の行を前後で比べれば、テストが書かれている 270 の場面すべてで FR-001 を確かめられる。`content_hash` も比べるので、重複防止のハッシュ（III）が変わらないことも分かる。

**Alternatives considered**:
- 本番に近いデータで両社を流して比べる：公式のページが毎回変わるので比べられない（spec Assumptions）。却下
- 固定ページで両社を1回流すテストを足す：テストの数が変わる（FR-002）。場面も 270 より少ない。却下

## R5: 臨時便の処理を両社でまとめるか（US3・FR-006）

**Decision**: **まとめない**。決まりが違うことを下の表に残す。共通にしたのは R1 の読み込みだけ。

| 処理 | マルエーフェリー（12） | マリックスライン（13） |
|---|---|---|
| 臨時便の行の目印 | `source_url` が船の詳細ページ（`!= SEARCH_URL`）。状態では見分けない | 状態 `extra` と `source_url`（便の詳細ページ） |
| 定期便の行とぶつかったとき | 便検索の行がいつも勝つ。臨時便の行は作らない | 定期便が欠航・運休・抜港・不明なら臨時便の行が勝つ（`_REPLACEABLE_BY_EXTRA`）。それ以外は定期便 |
| ぶつかったときの詳細の文 | 便検索の行に出港時刻があり臨時便と違うときだけ。詳細があれば `{詳細}（臨時便 HH:MM発あり）`、無ければ `臨時便 HH:MM発あり` | いつも `{詳細}（臨時便 HH:MM発あり）`。時刻が無ければ `（臨時便あり）` |
| ログ | `extra_voyage_key_conflict`（船・航路・港・日付・2つの出港時刻） | `extra_voyage_conflict`（キー・2つの URL） |
| 取り下げた臨時便の行を消す | 船ごとに、便（航路・終点の入港時刻）でまとめ、始発港の行があって出港が今より後で、今回書かなかったキーを消す | 一覧から消えた臨時便の URL のうち、出港前のものの `extra` の行を全部消す |
| 消してよいかの判断の範囲 | 詳細ページを取れて読めない臨時便が無かった船だけ（`ExtraParse.complete`） | 一覧にあるのに詳細ページを読めなかった臨時便は残す |
| 前の回の行を残す | 便検索の記録（`_recorded_search_keys_of`） | `_extra_rows_kept`・`_extra_first_departures` |

- 同じに見えるのは「`super()._upsert_departures()` のあとに消す」という順番だけ。中身（何を消すか）が全部違うので、Base にフックを足しても各社に今と同じ量のコードが残る
- 1つにまとめると、目印・勝ち負け・文・消す範囲の4つで会社ごとの分岐か設定が要る。spec US3 の「3つ以上なら、まとめない」に当たる

**Rationale**: 2社の公式の書き方（マルエーは船の詳細ページの告知、マリックスは便ごとの詳細ページ）が違い、それに合わせて 12・13 で決まりを別々に決めた。文の書き方やログの名前をそろえると振る舞いが変わる（FR-001・FR-007）。

**Alternatives considered**:
- ぶつかったときの文だけ共通の関数にする：書き方が違う（かっこの付け方・時刻が無いとき）ので、引数で分けることになり、読みにくくなるだけ。却下
- `BaseScraper` に「upsert のあとに呼ぶフック」を足す：今の2社の `_upsert_departures()` の上書き（数行）と変わらない。却下

## R6: マリックスラインの長いメソッド

**Decision**: この機能では触らない（spec Out of Scope・US3 で必要にならなかったため）。`_load_routes()`・`_load_stops()` を消すだけ。

**Rationale**: `_departures_from_detail()`（120 行）・`parse()`（109 行）・`_resolve_extra_conflicts()`（93 行）は長いが、1つの流れを上から読める形で、分けても読みやすさの得は小さい。分けるなら、3社目を足すときや 13 の仕様を変えるときに、その変更と合わせて決める。
