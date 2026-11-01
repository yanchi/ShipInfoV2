# Implementation Plan: スクレイパーを振る舞いを変えずに整理する

**Branch**: `17-scraper-refactor` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

---

## Summary

スクレイパーのコードの置き場所と重複だけを整理する。振る舞い（DB に書く行・ハッシュ・ログ・例外）は変えない。

- US1：`_load_routes()`・`_load_stops()` を `BaseScraper` に移す（R1）
- US2：`marue_ferry.py`（1788 行）をパッケージ `marue_ferry/` にし、役割ごとの mixin 5 つと `common.py`・`state.py` の 7 ファイル＋`__init__.py` に分ける。メソッドの中身は変えない（R2）。テストは差し替え先だけ直す（R3）
- US3：臨時便の処理は両社で決まりが違うので**まとめない**。違いを research R5 に残した
- 振る舞いが変わらないことは、DB を使う 270 テストの全部の行を前後で比べて確かめる（R4。変更前のコードで3回流して違い 0 を確認済み）

---

## Technical Context

**Language/Version**: Python 3.12（スクレイパー）
**Primary Dependencies**: SQLAlchemy・BeautifulSoup4・structlog（変更なし）
**Storage**: MySQL 8.0（本番）・SQLite in-memory（テスト）。スキーマの変更なし
**Testing**: pytest（`make test-scraper`：336 件）、比較用のプラグイン [snapshot_plugin.py](snapshot_plugin.py)・[compare_snapshots.py](compare_snapshots.py)、`make lint-scraper`（ruff）、`make check-schema`
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`。イメージを作り直すだけ）
**Project Type**: スクレイパー（Python パッケージ `scraper`）
**Performance Goals**: 変わらない（同じメソッドを同じ順に呼ぶ。import が数ファイル増えるだけ）
**Constraints**:
- DB に書く行・`raw_html_hash`・`content_hash` を変えない（FR-001）
- テストの期待値・入力・件数を変えない。差し替え先だけ直す（FR-002）
- 登録・クラス名・外から import している名前を変えない（FR-003）
- メソッドの中身を変えない（移すだけ）。見つけたバグは別の Issue（FR-008）
**Scale/Scope**: `base.py`・`marix_line.py`・`marue_ferry.py`（→ `marue_ferry/` 8 ファイル）、`tests/test_marue_ferry.py` の差し替え先（3 か所）

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立・疎結合 | ✅ PASS | `MarueFerry` は mixin を通して `BaseScraper` を継承したまま。両社の共通は Base の読み込み2つだけで、会社どうしは依存しない |
| II. Twig + Controller、スクレイパーは DB に直接書く | ✅ PASS | Web に触らない |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | ハッシュ・キー・ログの中身を変えない。前後の比較で `content_hash` も確かめる（R4） |
| IV. Docker で完結 | ✅ PASS | 比較の手順もコンテナの中で動く（quickstart） |
| V. フェーズごとにコミット | ✅ PASS | US1・US2 の区切りごとに、テストと比較を通してからコミット（FR-010） |
| 技術スタック・コーディング規約 | ✅ PASS | 変更なし。ruff で lint・フォーマット |
| ディレクトリ規約（2.1.0：大きくなったら `scrapers/<company_name>/` のパッケージにしてよい） | ✅ PASS | マルエーは `scrapers/marue_ferry/`。import の名前 `scraper.scrapers.marue_ferry` と登録するクラスは同じ。パッケージの中はマルエーのコードだけ。この機能に合わせて Constitution を 2.0.0 → 2.1.0 に直した |
| Governance「技術的負債は即日解消」 | ✅ PASS | この機能そのものが負債の解消 |

**Phase 1 設計の後に再チェック**: 違反なし。

---

## Project Structure

### Documentation

```
specs/17-scraper-refactor/
├── spec.md
├── research.md                  # R1〜R6
├── data-model.md                # DB は変更なし・マルエーの状態の一覧
├── quickstart.md                # 比較の手順
├── contracts/scraper-interface.md   # 前後で変えないもの
├── snapshot_plugin.py           # 比較用（リポジトリのテストには入れない）
├── compare_snapshots.py
├── log_events.py                # ログの出来事の一覧（FR-007）
├── checklists/requirements.md
├── plan.md                      ← このファイル
└── tasks.md                     （/speckit.tasks で生成）
```

### 変更対象

```
scraper/scraper/scrapers/base.py                 # _load_routes・_load_stops を足す
scraper/scraper/scrapers/marix_line.py           # 同じものを消す
scraper/scraper/scrapers/marue_ferry.py          # → 消える（git mv で __init__.py へ）
scraper/scraper/scrapers/marue_ferry/
├── __init__.py
├── common.py
├── state.py
├── fetch.py
├── ships.py
├── voyages.py
├── extra.py
└── statuses.py
scraper/tests/test_marue_ferry.py                # fixed_now・no_sleep・settings の差し替え先だけ
```

`scrapers/__init__.py`（登録）・`db/`・`utils/`・`tests/test_marix_line.py`・`tests/test_base_*.py`・Web アプリには触らない。

---

## Phases

### Phase A：比較の土台（R4）

- コードに触る前に、quickstart の 1 で `before1.jsonl`・`before2.jsonl`（270 行）とログの出来事の一覧 `events_before.txt` を取る
- 取っただけではコミットしない（`/tmp` のファイル。プラグインと比較のスクリプトは plan と一緒にコミット済み）

### Phase B：共通の読み込み（US1・R1・FR-004）

- `BaseScraper` に `_load_routes()`・`_load_stops()` を足す（マリックスの docstring つきの形）
- `marix_line.py`・`marue_ferry.py` から同じメソッドを消す。使わなくなった import（`Route`・`RouteStop` など）を消す
- テスト・lint・`check-schema`・比較（quickstart の 2）→ コミット

### Phase C：マルエーをパッケージにする（US2・R2・R3・FR-005）

1つのステップごとにテストと比較を通し、コミットする（どこで止めても動く。FR-010）。

1. `git mv marue_ferry.py marue_ferry/__init__.py`（中身はそのまま。履歴を追えるように、移すだけのコミットを先に作る）
2. `common.py` を作る：定数・dataclass・正規表現・モジュール関数を移し、`__init__.py` から import する
3. `state.py` を作る：`MarueState(BaseScraper)` に `__init__`・状態の型注釈（data-model）・マルエーだけの読み込みを移す。`MarueFerry` は `MarueState` を継承する
4. mixin を1つずつ作る：`fetch.py` → `ships.py` → `voyages.py` → `extra.py` → `statuses.py`。1つ移すたびに `MarueFerry` の基底に足し、クラスの本体から消す
   - 移したモジュールが時計（`date`・`datetime`）・`time`・`settings` を読むようになったら、同じステップで `tests/test_marue_ferry.py` の差し替え先に足す（R3）
5. `__init__.py` を仕上げる：`class MarueFerry(StatusesMixin, ExtraMixin, VoyagesMixin, ShipsMixin, FetchMixin)` と `__all__`（contracts の 2）。モジュールの docstring を段落ごとに各ファイルへ移す（文は変えない）

各ステップで：
- メソッドは**切り取って貼るだけ**。名前・引数・中身・順番を変えない
- `ruff check`・`ruff format`
- `make test-scraper`（336 passed）・比較（`diffs=0`）

### Phase D：臨時便の処理（US3・R5・R6・FR-006）

- コードの変更なし。research R5 の表（まとめない理由）で受け入れ条件 2・3 を満たす
- Phase C のあとに `extra.py` とマリックスの臨時便の処理を並べて読み、R5 の表が実装と合っているか見直す。違えば表を直す（まとめる判断に変わったら、そのときだけ別のステップを足す）

### Phase E：仕上げ

- quickstart の 3（行数・重複が無いこと）
- `make test-scraper`・`make lint-scraper`・`make check-schema`・`make verify-prod`（本番用イメージで import が通るか）
- 比較（`diffs=0`）

---

## Complexity Tracking

| 増えるもの | なぜ要るか | もっと簡単な案を採らない理由 |
|---|---|---|
| `marue_ferry/` パッケージ | 1788 行を役割ごとに分けつつ、`scraper.scrapers.marue_ferry` の import と登録を変えないため（Constitution 2.1.0 で許した形） | `scrapers/` の直下に `marue_ferry_extra.py` などを並べると、どれが登録されたスクレイパーか分かりにくい（R2） |
| mixin 5 つと `MarueState` | 状態を共有した1つのクラスを、メソッドの中身を変えずに分けるため | 委譲・関数に分けると状態を引数で渡すことになり、メソッドをほぼ全部書き換える（振る舞いが変わるリスク・テストの呼び出しも変わる。R2） |

減るもの：`_load_routes()`・`_load_stops()` の重複（2か所 → 1か所）、1788 行のファイル（→ どれも 600 行以下）。
