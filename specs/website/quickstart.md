# Quickstart: 運航情報Webサイト

**Feature**: website
**Date**: 2026-03-07

実装完了後の動作確認手順。

---

## 前提

```bash
make up       # Docker起動
make migrate  # マイグレーション実行（DBスキーマ変更なしだが念のため）
```

---

## 1. トップページ確認

```bash
open http://localhost:8080/
```

**期待動作**:
- 「ShipInfo - フェリー運航情報」ヘッダーが表示される
- 本日の日付タイトルが表示される
- マルエーフェリー・マリックスラインの運航状況が一覧表示される
- DBに当日データがない場合は「現在情報がありません」が表示され、500にならない

---

## 2. 会社別ページ確認

```bash
open http://localhost:8080/company/1   # マルエーフェリー
open http://localhost:8080/company/2   # マリックスライン
```

**期待動作**:
- 「< トップへ戻る」リンクがある
- 会社名が表示される
- 直近3日分の運航状況が日付ごとに表示される
- 欠航の場合は `statusDetail`（理由）が表示される

---

## 3. 404確認

```bash
curl -o /dev/null -s -w "%{http_code}" http://localhost:8080/company/999
# → 404 が返ること
```

---

## 4. モバイル表示確認

Chromeデベロッパーツール → デバイスモード（iPhone SE等）で `http://localhost:8080/` を確認:
- 横スクロールが発生しないこと（SC-003）

---

## 5. ステータス色確認

| ステータス | 期待表示 |
|---|---|
| operating | 緑（Bootstrap `text-success` or `badge bg-success`） |
| cancelled | 赤（Bootstrap `text-danger` or `badge bg-danger`） |
| delayed | 黄（Bootstrap `text-warning` or `badge bg-warning`） |
| suspended | グレー（Bootstrap `text-secondary`） |
| unknown | グレー（Bootstrap `text-secondary`） |

---

## 6. PHPUnitテスト実行

```bash
make test-php
```

全テストがグリーンであること。
