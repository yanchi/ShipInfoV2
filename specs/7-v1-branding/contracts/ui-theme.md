# UI Contract: V1 のテイスト

全ページ（トップ・港別・会社別・エラー）で共通。値は V1 の `ship_info/public/css/styles.css` から写す。

## `<head>`

上から次の順で出す（`base.html.twig`）。

```html
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{scheme+host+path}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{scheme+host+path}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="鹿児島〜沖縄フェリー運航情報サービス">
<meta name="twitter:card" content="summary">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<!-- Bootstrap CSS（今のまま）、共通 CSS（_site_styles.html.twig） -->
<!-- 本番かつ GOOGLE_ANALYTICS_ID があるときだけ gtag.js（V1 と同じコード） -->
```

- `og:image` は出さない（FR-008）
- `<html lang="ja" data-bs-theme="light">`
- 「ShipInfo」の文字列は HTML のどこにも出さない（FR-003）

## 色・書体（CSS 変数）

| 変数 | 値 | 用途 |
|---|---|---|
| `--v1-primary` | `#0073e6` | ヘッダーの帯、見出しの下線、リンク（`--bs-primary`・`--bs-link-color` にも入れる） |
| `--v1-text` | `#333` | 本文（`--bs-body-color`） |
| `--v1-text-muted` | `#555` | 補足 |
| `--v1-text-light` | `#666` | 「情報なし」の表示 |
| `--v1-bg` | `#f4f4f9` | ページの背景（`--bs-body-bg`） |
| `--v1-bg-light` | `#f9f9f9` | 「情報なし」の背景 |
| `--v1-border` | `#ddd` | 区切り線 |
| `--v1-footer-bg` | `#333` | フッターの帯 |
| `--v1-warning-text` | `#c0392b` | 注意書き（FR-016） |
| 書体 | `"Hiragino Kaku Gothic Pro", "Yu Gothic", YuGothic, Arial, sans-serif` | `--bs-body-font-family` |

`:root { color-scheme: light; }`。ダークモードの端末でも同じ配色。

## ヘッダー

```text
┌──────────────────────────────────────────────┐  背景 #0073e6、文字は白
│     鹿児島〜沖縄・奄美大島 フェリー運航情報      │  ← トップへのリンク。太字・中央
│           トップ   港別   各社 ▾               │  ← 太字・中央・1行（375px でも）
└──────────────────────────────────────────────┘
```

- サイト名：1.8rem（768px 以下 1.5rem、480px 以下 1.25rem）。「鹿児島〜沖縄・奄美大島」と「フェリー運航情報」の境目でだけ折り返す。`<h1>` にはしない
- ナビ：白・太字・下線なし、hover で下線。今いるページは `aria-current="page"` と常に下線
- 「各社 ▾」のメニュー：白地・濃い文字・角丸＋影。日付ボタン（sticky）より手前（`z-index`）
- 768px 以下でナビの文字を小さくする（V1 の body 0.9rem に合わせる）。縦には積まない
- エラーページのナビは「トップ」「港別」だけ

## 最終確認時刻・古い情報の警告

位置・文言は今のまま（ヘッダーの下）。警告は Bootstrap の `alert-warning`（黄色）のまま、グレーの背景の上で目立つ。

## 本文

| 要素 | 見た目 |
|---|---|
| ページの `<h1>`、日付ごとの `<h2>` | 青い下線（`border-bottom: 2px solid #0073e6`・`padding-bottom: .5rem`） |
| `.card`（要約・凡例・便の一覧・会社カード） | 白地・角丸 8px・`box-shadow: 0 2px 4px rgba(0,0,0,.1)`・枠線なし |
| 情報なし（「現在情報がありません。」など） | `.no-data`：背景 `#f9f9f9`・角丸 5px・斜体・`#666`・中央寄せ |
| 本文の注記（「運航情報はスクレイピングにより…」） | 今のまま（小さい灰色の文字）。要素は `<p class="page-note">` |

## ステータスのバッジ

形は全部共通：`display: inline-block`・太字・`padding: .2rem .6rem`・`border-radius: 12px`・`font-size: .85em`。

| 状態 | 表示（記号・文言は変えない） | クラス | 背景 | 文字 |
|---|---|---|---|---|
| 通常運航 | ✓ 通常運航 | `status-badge status-badge--operating` | `#d4edda` | `#155724` |
| 条件付・遅延 | ▲ 条件付・遅延 | `status-badge status-badge--delayed` | `#fff3cd` | `#856404` |
| 欠航 | ✗ 欠航 | `status-badge status-badge--cancelled` | `#f8d7da` | `#721c24` |
| 運休 | ■ 運休 | `status-badge status-badge--suspended` | `#e2e3e5` | `#383d41` |
| 情報なし | ？ 情報なし | `status-badge status-badge--muted` | `#e2e3e5` | `#6c757d` |
| 不明 | ？ 不明 | `status-badge status-badge--muted` | `#e2e3e5` | `#6c757d` |
| 運航予定 | ○ 運航予定 | `status-badge status-badge--scheduled` | 白、`1px dashed #6c757d` の枠 | `#333` |
| 便なし | — 便なし | `status-none text-secondary`（今のまま） | なし | 灰色 |

- Bootstrap の `.badge` クラスは付けない
- V1 の「寄港地変更（青）」「スケジュール変更（紫）」は V2 にステータスが無いので作らない（research R3）

## 異常の行（`port-entry--alert`）

5-ui-readability の「左の太い線・薄い背景・太字」を保つ。

| 状態 | 左の線（4px） | 背景 |
|---|---|---|
| 欠航 | `#721c24` | `#fdf2f3` |
| 条件付・遅延 | `#856404` | `#fffbeb` |
| 運休 | `#383d41` | `#f3f4f5` |

## 注意書き（FR-016）

`_status_warning.html.twig`。ステータスが欠航・条件付・遅延のときだけ。

```html
<p class="status-warning">出港時間・寄港地が変更になってる可能性があるので公式サイトをご確認ください</p>
```

`color: #c0392b; font-size: .85em; margin: 0 0 .3rem;`。便の行・トップの会社カードの航路・会社別の航路の要約の、バッジの下に出す。

## フッター

```html
<footer class="site-footer"><p>© 2025 鹿児島〜沖縄・奄美大島 フェリー運航情報サービス</p></footer>
```

背景 `#333`・白文字・中央・`padding: 1rem 0`・`margin-top: 2rem`。768px 以下で `font-size: .8rem`。

## 幅

375px〜1280px 以上で横スクロールが出ない（FR-015・SC-004）。本文の幅は今の `.container` のまま。
