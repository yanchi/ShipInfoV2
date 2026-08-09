# Quickstart — トップページ会社カード横並びグリッド

**Feature**: `1-company-card-grid` | **Date**: 2026-03-08

---

## 1. 環境起動

```bash
make up          # Docker 起動
make fixtures    # テストデータ投入（会社カードが複数必要）
```

ブラウザで http://localhost:8080 を開く。

> **Note**: グリッドの検証には会社が3社以上あると分かりやすい。フィクスチャが2社しかない場合は
> [AppFixtures.php](../../app/src/DataFixtures/AppFixtures.php) を確認するか、phpMyAdmin（`make up-tools` → http://localhost:8081）で
> `ferry_companies` にダミー会社を追加する。

---

## 2. 自動テスト

```bash
make test-php
```

追加される検証（[StatusControllerTest.php](../../app/tests/Controller/StatusControllerTest.php)）:

| テスト | 検証内容 | 対応FR |
|---|---|---|
| `testIndexRendersCompanyGrid` | `.row.row-cols-1.row-cols-md-2.row-cols-lg-3` が存在する | FR-001〜004 |
| `testCompanyCardsAreGridColumns` | `.row > .col > .card.h-100` の構造になっている | FR-001, SC-004 |
| `testIndexKeepsCardContent` | カード内に会社名リンク・航路名・バッジが残っている | FR-005 |

既存の4テスト（`testIndexReturns200` 等）もそのまま通ること。

---

## 3. 手動確認（レスポンシブ）

CSS の折り返し結果はサーバーサイドテストで検証できないため、ブラウザで目視確認する。

Chrome DevTools → デバイスツールバー（`Cmd + Shift + M`）で幅を変えて確認:

| 幅 | 期待する列数 | 対応FR / SC |
|---|---|---|
| 375px（iPhone SE） | **1列**・カードが画面幅いっぱい・バッジのテキストが読める | FR-004, SC-003 |
| 800px（タブレット） | **2列** | FR-003 |
| 1200px（デスクトップ） | **3列** | FR-002 |

### 併せて確認すること

- [ ] 同一行のカードの高さが揃っている（航路数が違ってもカード下端が一直線） … SC-004
- [ ] 会社名リンクをクリックすると会社詳細ページ（`/company/{id}`）に遷移する … FR-005
- [ ] 公式サイトリンクが別タブで開く … FR-005
- [ ] 運航状況バッジの色とテキストが変更前と同じ … FR-005
- [ ] 行間が空きすぎていない（`mb-4` 削除漏れがあると二重に空く） … R-004
- [ ] 縦スクロール量が変更前より減っている … SC-001

---

## 4. エッジケース確認

| ケース | 確認方法 | 期待結果 |
|---|---|---|
| 会社0件 | `ferry_companies` を空にする（または全社を無効化） | `現在情報がありません。` の alert が表示され、レイアウト崩れなし |
| 会社1社のみ | 1社だけ残す | カード1枚が左寄せで表示され、横に伸びきらない |
| 航路0件の会社 | 航路を持たない会社を追加 | カード内に `航路情報がありません。` が表示される |
| 会社10社以上 | ダミー会社を追加 | 3列で正しく折り返し、崩れない |

---

## 5. ロールバック

Twig テンプレート1ファイルの変更のみなので、切り戻しは以下で完了する。

```bash
git checkout -- app/templates/status/index.html.twig
```

DB マイグレーション・キャッシュクリア・アセットビルドはいずれも不要。
