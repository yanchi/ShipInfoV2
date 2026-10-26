# Implementation Plan: 先の便にも公式の便ごとの状態を出す

**Branch**: `11-marue-voyage-lines` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

---

## Summary

マルエーフェリーのスクレイパーだけを変える。画面・通知・DB は変えない。

- 便の行と便の照合を `_voyage_line()` にまとめる。出港日の一致を優先し、途中の港から書いた行だけを範囲で照合する（R1・R7）
- 今の便：便の行が読めるのに合わず、まだ出港していなければ operating（R2・R7）
- 先の便：合う行があればその状態を全港に出す。港別情報は使わない（R3）
- 「臨時便運航」を operating として読む（R4）
- `fetch()` で鹿児島航路ページを先に読み、便の行がある2日先以降の日付は間隔に関係なく検索する（R5）

---

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: requests, BeautifulSoup4 (lxml), SQLAlchemy 2.0
**Storage**: MySQL 8.0。スキーマの変更なし
**Testing**: pytest（2026-10-26 の保存版を fixture にする）
**Target Platform**: Docker Compose（本番はさくら VPS の `compose.prod.yml`）
**Project Type**: スクレイパー
**Performance Goals**: 便の行が無い日付の検索回数は変えない。便の行がある日付と、前回状態を付けた日付（DB の行で船名があり、欠航・運休・条件付のどれか。T016b）だけ、2日先以降の検索が1回の実行で十数回まで増える
**Constraints**:
- `BaseScraper.fetch()` / `parse()` / `parse_departures()` のシグネチャは変えない
- `raw_html_hash` に使う文字列は、航路ごとの「今日の始発港の便が出港済みか」を末尾に足す以外は変えない（出港時刻をまたぐと航路単位の判定が変わるため）
- 出港済みの行は確定（`freeze_after_departure`）のまま
**Scale/Scope**: `marue_ferry.py` 1ファイルとテスト。急ぎ（10/27 07:00 那覇発の便の前にデプロイ）

未解決の NEEDS CLARIFICATION は無い。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパーは `BaseScraper` 継承・会社ごとに独立 | ✅ PASS | `MarueFerry` の中だけ。Base・`utils/` は変えない |
| II. Twig + Controller、API なし、スクレイパーは DB に直接書く | ✅ PASS | Web アプリは変えない |
| III. `raw_html_hash`・キーごとの最新状態・`scraper_logs` | ✅ PASS | 書き方は変えない。先の便の行に状態が入るだけ。出港済みの今の便のために `departure_statuses` を読む（`_recorded_voyages()` と同じく読むだけ）。`voyage_not_in_excerpt` に `assumed` を足して判断を追えるようにする |
| IV. Docker で完結 | ✅ PASS | マイグレーションなし。新しいライブラリなし |
| V. フェーズごとにコミット | ✅ PASS | 下の Phase A〜C を tasks.md のグループにして、グループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 変更なし |

**Phase 1 設計の後に再チェック**: 違反なし。FR-011 は「公式は変更のある便に行を書く」という前提に乗る。外れたときの影響は出港前の今の便だけで、出港済みの便は前回記録したステータスに港ごとに戻す（R7）。

---

## Project Structure

### Documentation

```
specs/11-marue-voyage-lines/
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── samples/                 # 2026-10-26 の保存版（証跡）
├── checklists/requirements.md
├── plan.md                  ← このファイル
└── tasks.md                 （/speckit.tasks で生成）
```

contracts/ は作らない（画面・通知・DB の形は変わらない）。

### 変更対象

```
scraper/scraper/scrapers/marue_ferry.py            # R1〜R7、docstring
scraper/tests/test_marue_ferry.py                  # 新しいテスト、既存1件の期待値変更（R2）
scraper/tests/fixtures/marue/kagoshima_20261026.html   # 新規（samples のコピー）
specs/4-departure-port-status/spec.md              # FR-021 の書き換え（FR-008）
```

---

## Phases

### Phase A：読み取り（US2）

- `_parse_status_text()` に「臨時」→ operating（R4）
- `VoyageStatus.from_midway` と `_VOYAGE_LINE` の港名の取り出し（R7）
- テスト：2026-10-26 の fixture で警告0件・波之上の便の行3つ・タグは cancelled（SC-002）

### Phase B：照合と判定（US1・US3）

- `_voyage_line()`（R1・R7）、`_for_voyage()` の書き換え（R2・R7）、出港済みの判定
- `parse_departures()` の先の便（R3）、`_route_status()`（R6）
- 既存の `test_voyage_not_in_excerpt_keeps_ship_status` は結果を変えず、名前だけ `test_departed_voyage_not_in_excerpt_keeps_ship_status` に変える（R2）
- テスト：SC-001（10/27 那覇発上りが全港 cancelled）、10/25 便が出港済みで前回の記録（無ければタグ）のまま、FR-011 で operating・前回の記録にした今の便に港別情報が付かない、SC-006（10/29 便が operating）、行0のときタグ、途中の港の行が範囲で合う、先の便に港別情報が付かない、行の無い先の便は None（SC-004）

### Phase C：検索の追加（FR-010）と文書

- `fetch()` の順番の入れ替えと、便の行による2日先以降の検索（R5）
- テスト：便の行がある2日先のキーは間隔内でも検索、無いキーは今までどおり飛ばす（SC-005）。DB に status のある2日先のキーも検索する（行が消えたとき。R5）
- docstring、4-departure-port-status の FR-021 の書き換え
- `make test-scraper`・`make lint-scraper`

---

## Complexity Tracking

なし。
