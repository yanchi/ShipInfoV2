# Research: マルエーフェリー情報取得方式変更

**Date**: 2026-03-08
**Branch**: `2-marue-fetch-update`

---

## 1. 鹿児島航路ページ HTML 構造（実サイト確認済み 2026-03-08）

**URL**: `https://www.aline-ferry.com/kagoshima/`
（参考: `/status/status-route/route-kagoshima` も同構造の運航状況ページとして存在）

### 確認済み構造（スクレイパー実装時に実サイトで再確認済み）

```html
<!-- 船ごとに繰り返し。a タグがブロック全体を囲む -->
<a href="/status/route-kagoshima/ferry-akebono/21525/">
  <div class="route-head">
    <div class="ferry-name">フェリーあけぼの</div>
    <div class="route-detail">鹿児島 - 名瀬 - 亀徳 - 和泊 - 与論 - 本部 - 那覇</div>
  </div>
  <div class="tag-list">
    <span class="tag-normal">通常運航</span>
  </div>
  <div class="situation-excerpt">通常運航致しております。</div>
</a>
```

**修正**: 当初 `h3/p` 構造と推測していたが、実際は `div.ferry-name` + `span.tag-*` + `div.situation-excerpt` 構造。スクレイパー実装時に実サイト確認で修正済み。

### 重要な確認事項

| 項目 | 状況 |
|---|---|
| 上り・下り便の区別 | なし（船単位のステータス、上り・下り両方向に共通適用） |
| 日付情報 | なし（「○○年○○月○○日更新」は更新日であり valid_date ではない） |
| ステータスのCSSクラス | なし（`<h4>` や `<p>` のテキスト内容のみで判定） |
| CMSプラットフォーム | WordPress ブロックエディタ |

### ステータステキストマッピング

| 表示テキスト（例） | OperationStatusEnum |
|---|---|
| `通常運航` | `operating` |
| `条件付運航` / `条件付き` | `delayed` |
| `欠航` | `cancelled` |
| `運休` | `suspended` |
| `遅延` / `スケジュール変更` | `delayed` |

---

## 2. 検索エンドポイント HTML 構造（実サイト確認済み 2026-03-08）

**URL**: `https://www.aline-ferry.com/search/result.php`
**Method**: POST

### パラメータ（実証済み）

| パラメータ名 | 値 | 意味 |
|---|---|---|
| `startDate` | `YYYY-MM-DD` | 出航日（当日） |
| `startPort` | `50` | 出発港コード（鹿児島） |
| `endPort` | `83` | 到着港コード（那覇） |

### レスポンス HTML 構造（確認済み）

ページタイトル:
```html
<title>2026年3月8日 乗船検索結果 | A''LINE ...</title>
```

結果テーブル（`div.result-box` 内）:
```html
<div class="result-box">
  <div class="responsive-table">
    <table class="s-result">
      <thead>
        <tr>
          <th>航路名</th><th>船名</th><th>乗船日時</th>
          <th>下船日時</th><th>距離</th><th>会社名</th><th>運賃表</th>
        </tr>
      </thead>
      <tbody>
        <!-- 便あり: 1行以上 -->
        <tr>
          <td><a href="../kagoshima">鹿児島航路</a></td>
          <td>※下記参照</td>
          <td>－</td><td>－</td><td>－</td>
          <td colspan="2"><a href="attention.php">マリックスライン♁</a></td>
        </tr>
        <!-- 便なし: tbody が空、または行なし -->
      </tbody>
    </table>
  </div>
</div>
```

### 運航有無判定方法（確定）

```python
# 便あり判定: table.s-result の tbody に tr が1行以上ある
has_service = bool(soup.select("table.s-result tbody tr"))
```

### valid_date の取得（確定）

`valid_date = POST で渡した startDate（= date.today()）`

レスポンスHTMLから日付をパースする必要はない。POSTパラメータ `startDate` が即ち valid_date。

### 重要な発見: 共同運航

検索結果の「会社名」欄が「マリックスライン」になることがある（共同運航）。
→ 本スクレイパーは「鹿児島航路で便があるか」を判定するだけでよく、会社名は無視する。

---

## 3. 設計判断

### Decision 1: 検索は下り便のみ、両方向に共通適用
- **Rationale**: 鹿児島ページに上り・下り区別がない。下り便の有無で「本日の鹿児島航路の運航有無」を判定し、両方向に適用するのが最もシンプル。
- **Alternatives considered**: startPort=83, endPort=50 で上り便も別途検索 → 複雑さ増、不採用

### Decision 2: valid_date = startDate（= today）
- **Rationale**: POSTパラメータに当日日付を渡しているため、valid_date は常に today。レスポンスHTMLのパース不要。（鹿児島ページに日付なし、検索レスポンスの `乗船日時` 欄が「－」の場合もある）
- **Fallback**: 不要（startDate は常に date.today() で確定）

### Decision 3: 運航有無判定は `table.s-result tbody tr` の存在で行う
- **Rationale**: 実サイトで確認。tbody に行があれば便あり、なければ便なし。
- **Alternatives considered**: テキスト検索（「該当なし」等）→ テーブル構造の方が安定

### Decision 4: 鹿児島ページで `h4` または `p` のステータステキストが見つからない場合はスキップ
- **Rationale**: CSSクラスによる判定ができないためテキストマッチが必須。見つからない = 構造変更の可能性。

### Decision 5: raw_html_hash は鹿児島ページの HTML で計算
- **Rationale**: 鹿児島ページがステータスのメインソース。検索結果は二値判定のみ。

---

## 4. リスクと対策

| リスク | 対策 |
|---|---|
| `table.s-result` が消えた場合 | warning ログを記録、安全側（便ありとして鹿児島ページへ進む）に倒す |
| 共同運航でマリックスラインが担当する日の判定 | 会社名を無視し「便の存在」のみで判定するため問題なし |
| 鹿児島ページのステータステキストが変わった場合 | ステータス判定に失敗 → warning + スキップ |
| WordPress テーマ更新による HTML 構造変化 | h2("鹿児島航路") を起点にした解析で耐性を持たせる |
