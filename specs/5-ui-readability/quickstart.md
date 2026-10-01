# Quickstart: 運航情報画面の見やすさ改善

## 準備

```bash
make up
make migrate
make scraper-run   # 最新のデータを入れる
```

ブラウザで http://localhost:8080 を開く。スマートフォン幅の確認は、開発者ツールのデバイス表示で幅 375px にする。

## PR1: 港別ページとステータス表示

1. `/ports` を開く → 全港・両方向が表示され、上部に日付ボタン、凡例（開閉できる）がある
2. 出発港「和泊」・方向「下り」を選んで表示する → リダイレクトされて URL が `/ports?port={和泊のID}&dir=down` になり、各日付に「和泊発→那覇」だけが出る。「和泊発のみ表示中」と「全港に戻す」が出る
3. この時点では保存されていない：`/ports` を開き直す → 全港表示
4. 「和泊・下り」を選んで「この港を保存」→ `/ports?port={和泊のID}&dir=down` にリダイレクトされる。`/ports` を開き直す → 和泊・下りのまま
5. 「全港に戻す」→ 全港表示になる。`/ports` を開き直す → 和泊・下りのまま（保存は残る）
6. 別の港の URL（`/ports?port={名瀬のID}`）を開く → 名瀬で表示。`/ports` を開き直す → 和泊・下りのまま
7. 「保存を解除」→ `/ports` を開き直すと全港表示
8. 下までスクロール → 日付ボタンが上に残る。押すとその日付に移動し、見出しがボタンに隠れない
9. 確認時刻が方向の見出しに1回だけ出て、行ごとには出ない（違う時刻の行だけ行に出る）
10. 異常の確認：DB で1行を欠航にして表示を見る

   ```sql
   UPDATE departure_statuses SET status = 'cancelled'
   WHERE departure_date = CURDATE() + INTERVAL 1 DAY LIMIT 1;
   ```

   → 上部の要約に出て、押すとその行に移動する。行は左の線・薄い背景・太字で目立つ。和泊に絞り込むと「絞り込みの外にも欠航・条件付などがあります（1件）」が出る
11. 今日の便で出港時刻を過ぎたものが薄く「出港済み」になる。条件付・欠航・運休の便は薄くならない
12. `/ports?port=999`、`/ports?dir=xxx` → エラーにならず全港表示。保存した港は変わらない。`/ports?port={名瀬のID}&save=1`・`/ports?clear=1` を開いても保存した港は変わらない
13. 画面の高さ：375 × 667 で、欠航を4件作って開く → 共通ヘッダー・日付ボタン・要約（3件＋「ほか1件」）・最初の行がスクロールせずに見える（SC-003・SC-004）
14. レスポンスヘッダーに `Cache-Control: private` と `Vary: Cookie` がある（`curl -I localhost:8080/ports`）

## PR2: トップ

1. Cookie なしで `/` → 異常の要約、「自分の港の便を見る」ボタン、会社一覧。方向ごとの便の概要は無い
2. `/ports` で港を保存してから `/` → その港の今日の便が出る。375 × 667 で要約とその便がスクロールせずに見える
3. その日便の無い会社が「本日運航なし」の1行になる
4. 要約の項目を押す → `/ports?port=all#r-...` で該当の行に着地する。保存した港は変わらない

## PR3: 会社別ページと共通ヘッダー

1. `/company/1` → 今日〜3日先が並び、昨日以前は無い。各日付に航路の要約行（情報があれば）と便の行
   - 便が無いと確認できた日は「便なし」、まだ取得していない日（例：3日先でマルエーの検索前）は「情報なし」になる
2. 全ページに共通ヘッダー（トップ・港別・各社）と最終確認時刻がある
3. 古い情報の警告：先にスクレイパーを止める（動いていると次の実行で `checked_at` が上書きされる）

   ```bash
   docker compose stop scraper
   ```

   - DB で1社分の `checked_at` だけを2時間以上前にする → もう1社が新しくても、全ページ上部に「情報が古い可能性があります」とその会社名が出る

     ```sql
     UPDATE departure_statuses d JOIN routes r ON r.id = d.route_id
     SET d.checked_at = NOW() - INTERVAL 3 HOUR WHERE r.ferry_company_id = 2;
     ```

   - 1社分の前日以降の行を消す（長く止まった状態）→ 警告とその会社名が出たまま

     ```sql
     DELETE d FROM departure_statuses d JOIN routes r ON r.id = d.route_id
     WHERE r.ferry_company_id = 2 AND d.departure_date >= CURDATE() - INTERVAL 1 DAY;
     ```

   - 確認が終わったら `make scraper-run` でデータを戻し、`docker compose start scraper` で再開する

## テスト

```bash
make test-php
```
