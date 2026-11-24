# Quickstart: 検索語に合わせた会社ページの説明文と船の名前

## 公開前に確かめる（SC-001）

```bash
make up
make migrate

# 会社ページのタイトル・説明文
curl -s http://localhost:8080/company/2 | grep -o '<title>[^<]*</title>'
# → マリックスライン 運航状況 リアルタイム（今日・明日） | 鹿児島〜奄美・沖縄フェリー運航情報
curl -s http://localhost:8080/company/2 | grep -o '<meta name="description" content="[^"]*"'
# → …の運航（運行）状況をリアルタイムで。…運航船：クイーンコーラルクロス・クイーンコーラルプラス。

# 船の名前・別名の1行
curl -s http://localhost:8080/company/1 | grep -o '<p class="company-aliases[^<]*</p>'
# → 運航船：フェリー波之上・フェリーあけぼの ／ 別名：Aライン（エーライン）

# 「運行」は description と og:description にだけある（各ページ 2 回）
for p in / /ports /ports/kametoku /company/1 /company/2; do
  echo "$p $(curl -s http://localhost:8080$p | grep -o '運行' | wc -l)"
done
# → どれも 2

make test-php phpstan cs-php lint-php
make verify-prod
```

ブラウザで `/company/1` を 375px 幅で開き、1行が折り返して横スクロールが出ないことを見る。

## 公開後に確かめる（SC-002〜SC-005）

公開から 4 週間後に Search Console の「検索パフォーマンス」で、期間を公開日以降にして見る。

| 指標 | 見る場所 | 目標 |
|---|---|---|
| `/company/2` の CTR | ページ | 1.62% → 3% 以上（順位が ±1 位のとき） |
| `/company/1` の CTR | ページ | 2.12% → 3% 以上 |
| 船の名前・別名のクエリのクリック | クエリ（「波之上」「あけぼの」「クイーンコーラル」「Aライン」「エーライン」で絞る） | 4 回より多い |
| 平均掲載順位 | 全体 | 7.5 位より悪くならない |

## 船が入れ替わったとき

新しいマイグレーションで `ferry_companies` の `ship_names`（と必要なら `aliases`）を直す。

```php
$this->addSql('UPDATE ferry_companies SET ship_names = ? WHERE scraper_class = ?', ['["新しい船", "フェリーあけぼの"]', 'MarueFerry']);
```

このサイトが扱っていない会社の船は入れない（FR-008）。
