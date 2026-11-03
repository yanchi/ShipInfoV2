# Quickstart: 港ごとのページの確かめ方

```bash
make up
make migrate
make scraper-run   # 便のデータが無ければ
```

## 港のページ

1. http://localhost:8080/ports/kametoku を開く → 亀徳を出る便だけが出る。h1 は「徳之島（亀徳港）発の運航状況」
2. ソースを見る → `<title>` は「徳之島（亀徳港）発 フェリー運航状況（今日・明日） | 鹿児島〜奄美・沖縄フェリー運航情報」。canonical は `http://localhost:8080/ports/kametoku`
3. http://localhost:8080/ports/kametoku?dir=up → 上りだけが出る。canonical は `?dir=` 無し
4. http://localhost:8080/ports/xxx → 404
5. 港へのリンクの並びで、亀徳がリンクになっておらず、ほかの 6 港はリンクになっている

## 古い URL・フォーム・保存

```bash
curl -sI 'http://localhost:8080/ports?port=3&dir=down' | grep -iE '^(HTTP|location)'
# HTTP/1.1 301 / Location: /ports/<港3の slug>?dir=down
curl -sI 'http://localhost:8080/ports?port=all' | head -1   # 200
```

1. `/ports` の絞り込みで「和泊・両方向」を選んで「この港を保存」→ `/ports/wadomari` に移る
2. トップを開く → 「和泊発の今日の便」が出て、「4日分を見る」が `/ports/wadomari` を指す
3. `/ports` を開く → 保存した和泊が出る（転送しない）
4. `/ports/naze` を開く → 名瀬が出て、「保存を解除」が出る（保存は和泊のまま）

## sitemap・タイトル

```bash
curl -s http://localhost:8080/sitemap.xml | grep -c '/ports/'   # 7
curl -s http://localhost:8080/ | grep -o '<title>[^<]*'
curl -s http://localhost:8080/ports/kametoku | grep -c '運行'     # 0
```

## テスト

```bash
make test-php && make phpstan && make cs-php && make lint-php
```

## 公開後（Search Console）

1. sitemap を送り直す（`https://ship.isl-mentor.com/sitemap.xml`）
2. URL 検査で `/ports/kametoku` などの「インデックス登録をリクエスト」
3. 4 週間後に SC-002〜SC-004（インデックス・CTR・島名の検索）を確かめる
