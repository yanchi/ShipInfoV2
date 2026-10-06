# Quickstart: OG 画像を出す

## 1. 自動テスト

```bash
make test-php
make lint-php
make phpstan
make cs-php
```

この機能で変える・足すテスト：

- `StatusControllerTest::testHeadMetaOnAllPages`：3ページで og:image（絶対 URL）・type・width・height・alt と twitter:card = summary_large_image（SC-001）
- `ErrorPageTest::testNotFoundPageHeadMeta`：404 のページにも同じタグ
- 画像ファイル：`public/og-image.png` が PNG・1200×630・300KB 以下（SC-002）

## 2. 画像を作り直す

元は `specs/10-og-image/og-image.html`。macOS の Chrome で：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1200,630 \
  --screenshot=app/public/og-image.png \
  "file://$PWD/specs/10-og-image/og-image.html"
```

作ったら、画像を開いて目で確かめる（SC-004：幅 300px に縮めてもサイト名が読めるか）。`make test-php` で寸法・大きさも確かめる。

## 3. ローカルで確かめる

```bash
make up
curl -s http://localhost:8080/ | grep -E 'og:image|twitter:card'
curl -sI http://localhost:8080/og-image.png   # 200・image/png
```

## 4. 本番で確かめる（SC-003）

master に入れてデプロイした後：

```bash
curl -s https://ship.isl-mentor.com/ | grep -E 'og:image|twitter:card'
curl -sI https://ship.isl-mentor.com/og-image.png
```

カードの見え方は、Facebook のシェアデバッガー（https://developers.facebook.com/tools/debug/ ）などに `https://ship.isl-mentor.com/` を入れて確かめる。LINE・Slack は自分宛てに URL を貼って見る（キャッシュが残っていれば URL にクエリを付けて試す）。
