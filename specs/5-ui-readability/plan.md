# Implementation Plan: 運航情報画面の見やすさ改善

**Branch**: `5-ui-readability` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

---

## Summary

3画面（トップ・港別・会社別）の表示の構成と見せ方を変える。DB とスクレイパーは変えない。

- **港別ページ**：出発港・方向で絞り込む（表示は URL、保存はフォームで選んだときだけ Cookie）。異常の要約を上部に出す。行を「時刻とステータスが主」の2段にし、確認時刻を見出しにまとめる。日付ボタンで移動する
- **トップ**：異常の要約と、保存した港の今日の便（または港別ページへのボタン）を出す
- **会社別**：今日〜3日先を、航路の要約行と便の行で出す
- **共通**：ヘッダー、最終確認時刻と古い情報の警告、全ページで同じステータス表示

既存の `PortBoardBuilder` の判定ルールは変えない。絞り込み・会社別の選別・異常の要約は、組み上がったボードを加工する別のクラスで行う（research R4・R5・R13）。

---

## Technical Context

**Language/Version**: PHP 8.3
**Primary Dependencies**: Symfony 7.4, Doctrine ORM, Twig, Bootstrap 5.3（CDN、読み込み済み）
**Storage**: MySQL 8.0。変更なし（読み取りのリポジトリメソッドを2つ追加・1つ削除）
**Testing**: PHPUnit（表示用オブジェクト・Service の単体テスト、Controller の機能テスト）
**Target Platform**: Docker Compose（php / nginx / mysql）
**Project Type**: Web アプリ（MVP、Twig）
**Performance Goals**: 1リクエストあたりの DB クエリは今の `/ports` と同程度（ボード用2本＋最終確認時刻1本＋会社一覧1本）。最終確認時刻は `departure_date` で範囲を絞ってインデックスを効かせ、Twig 拡張の中でリクエストごとに1回だけ取る
**Constraints**:
- 新しいライブラリ・アセットのビルド環境は入れない。JS は絞り込みフォームの自動送信程度に留め、JS 無しでも全機能が動く
- `PortBoardBuilder` の判定ルールと既存テストは変えない（SC-009）
- 画面の幅 375px で横スクロールなし。高さ 667px で異常の要約と最初の行が最初の画面に入る
- `/` と `/ports` は Cookie で中身が変わるので `Cache-Control: private` と `Vary: Cookie` を付ける
**Scale/Scope**: 7港・2方向・4日。ボードは最大 48 行

未解決の NEEDS CLARIFICATION は無い（research.md で全部解決済み）。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ PASS | スクレイパーは変更しない |
| II. Twig + Controller、API なし | ✅ PASS | 既存の Controller と Twig を変える。API は作らない。絞り込みはクエリパラメータと Cookie でサーバー側で行う |
| III. データ品質・キーごとの最新状態 | ✅ PASS | DB を変えない。読み取りのみ |
| IV. Docker で完結 | ✅ PASS | 追加の環境は無い |
| V. フェーズごとにコミット・スコープを制限 | ✅ PASS | 下の PR1〜3 に分け、tasks.md のグループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | 新しいライブラリは入れない |

**Phase 1 設計の後に再チェック**: 違反は無し。

---

## Project Structure

### Documentation

```
specs/5-ui-readability/
├── spec.md
├── research.md
├── data-model.md
├── contracts/
│   ├── http-routes.md
│   └── ui-status.md
├── quickstart.md
├── plan.md          ← このファイル
└── tasks.md         （/speckit.tasks で生成）
```

### 変更対象

```
app/src/Controller/StatusController.php          # 3アクションとも変更
app/src/Service/PortFilterResolver.php           # 新規：クエリ・Cookie から PortFilter を作る
app/src/Service/PortAlertSummaryBuilder.php      # 新規：異常の要約
app/src/Twig/SiteExtension.php                   # 新規：会社ごとの最終確認時刻・古さ判定・会社一覧（リクエスト内で結果を覚える）
app/src/Enum/CompanyDayStateEnum.php             # 新規：便あり / 便なし / 情報なし
app/src/View/PortFilter.php                      # 新規
app/src/View/PortAlert.php                       # 新規
app/src/View/PortAlertSummary.php                # 新規
app/src/View/CompanyDay.php                      # 新規
app/src/View/PortBoard.php                       # filter() / forCompany() / lastCheckedAt()
app/src/View/PortBoardDirection.php              # commonCheckedAt()
app/src/View/PortBoardEntry.php                  # companyId、isAlert() / isDeparted() / checkedAtDiffersFrom()
app/src/Service/PortBoardBuilder.php             # エントリーに companyId を入れるだけ（判定ルールは変えない）
app/src/Repository/DepartureStatusRepository.php # findLatestCheckedAtByCompany()
app/src/Repository/FerryCompanyRepository.php    # findBoardCompanies()（情報の古さの判定の基準）
app/src/Repository/OperationStatusRepository.php # findUpcomingByCompany()、findRecentByCompany() を削除

app/templates/base.html.twig                     # 共通ヘッダー・最終確認時刻・古い情報の警告・共通 CSS
app/templates/status/_status_badge.html.twig     # contracts/ui-status.md に揃える
app/templates/status/_alert_summary.html.twig    # 新規：異常の要約（トップ・港別）
app/templates/status/_port_entry.html.twig       # 新規：便の行（港別・トップ・会社別）
app/templates/status/_status_legend.html.twig    # 新規：凡例
app/templates/status/ports.html.twig
app/templates/status/index.html.twig
app/templates/status/company.html.twig

app/tests/View/PortBoardTest.php                 # 新規
app/tests/View/PortBoardEntryTest.php            # 新規
app/tests/Service/PortFilterResolverTest.php     # 新規
app/tests/Service/PortAlertSummaryBuilderTest.php # 新規
app/tests/Repository/*                           # 追加メソッドのテスト。OperationStatusRepositoryTest の findRecentByCompany のテスト2件は削除
app/tests/Controller/StatusControllerTest.php    # 画面ごとのテストを追加・更新
```

**Structure Decision**: 既存の `app/src/View`（表示用オブジェクト）と `app/src/Service` の構成に合わせる。CSS は量が少ないので `base.html.twig` の `<style>` に置く（アセットのビルド環境を入れない）。

---

## 実装の分割（PR）

spec の Assumptions どおり、3つの PR に分ける。設計は全体で一度に決め（この plan）、実装は順番に行う。

| PR | 範囲 | spec | 主な変更 |
|---|---|---|---|
| **PR1** | 港別ページ＋ステータス表示の統一 | US1〜3、US6 の FR-024〜026 | `PortFilter*`、`PortAlert*`、`PortBoard*` の追加メソッド、`_status_badge`・`_alert_summary`・`_port_entry`・`_status_legend`、`ports.html.twig` |
| **PR2** | トップ | US4 | `index` アクション・`index.html.twig`（PR1 の部品を使う） |
| **PR3** | 会社別＋共通ヘッダー・最終確認時刻 | US5、US6 の FR-022・023 | `CompanyDay`・`CompanyDayStateEnum`、`findUpcomingByCompany()`、`findLatestCheckedAtByCompany()`、`SiteExtension`、`base.html.twig`、`company.html.twig` |

PR1 の `_status_badge` の変更はトップ・会社別にもそのまま効く（同じ部品を使っているため）。PR2・PR3 はどちらも PR1 だけに依存し、互いには依存しない。

---

## 主な設計判断（詳細は research.md）

| 判断 | 内容 | research |
|---|---|---|
| 絞り込み | クエリパラメータ（`port`・`dir`）でサーバー側で絞る。Cookie に保存するのはフォームで「保存」したときだけ。リンク・共有URLは保存を変えない | R1・R2 |
| 日付の移動 | アンカーと sticky のリンク。JS なし | R3 |
| 異常の要約 | 全港のボードから作り、絞り込みで「表示」と「外の件数」に分ける | R4 |
| ボードの加工 | ビルダーの判定は変えず、`PortBoard::filter()` / `forCompany()` で加工。会社は ID で突き合わせる | R5・R13 |
| 会社別の日付の状態 | 便あり・便なし・情報なしを、元の行の有無で区別 | R13 |
| 確認時刻 | 方向単位で分まで同じなら見出しに1回 | R6 |
| 最終確認時刻 | 会社ごとの `MAX(checked_at)` のうち最も古いもの。2時間で警告し、古い会社名も出す。前日以降の行が無い会社も古い扱い | R10 |
| キャッシュ | `/`・`/ports` に `Cache-Control: private`・`Vary: Cookie` | R15 |
| 画面の高さ | sticky は日付ボタンだけ、要約は3件まで出して残りは開閉 | R16 |

## Complexity Tracking

違反は無いので記載なし。
