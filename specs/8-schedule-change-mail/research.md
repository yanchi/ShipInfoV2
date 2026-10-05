# Research: 運航に変更がある便をメールで知らせる

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-06

調査時点の現状。

- **V1**（`../ShipInfo/python/src/notifier.py`）：Python の `smtplib` で送る。ホストの crontab（`0 0,6,15 * * *`）がスクレイパーを動かし、その直後に会社ごとに1通送る。設定は `SMTP_HOST`・`SMTP_PORT`・`SMTP_USER`・`SMTP_PASSWORD`・`NOTIFY_FROM`・`NOTIFY_TO`（カンマ区切り）。STARTTLS だが **証明書の検証をオフ**にしている（`check_hostname = False`・`CERT_NONE`）
- **V2 のスクレイパー**（`scraper/scraper/main.py`）：`schedule` で 30 分ごとに全社を取る常駐プロセス。メールの仕組みは無い
- **V2 の Web アプリ**（`app/`）：Symfony 7.4。Mailer・Messenger・Scheduler は入っていない。本番イメージ（`docker/production/app/`）は supervisord で nginx と php-fpm を動かす。cron は無い
- **V2 のステータス**：`OperationStatusEnum` は operating / delayed / cancelled / suspended / unknown / no_service の6つ。`departure_statuses.status` は null（運航予定）もある。V1 の「寄港地変更」「抜港」に当たる値は無く、#54 で航行経路変更は delayed、抜港は cancelled に寄せている
- **サイトの表示範囲**：港別ボード・会社別ページは今日〜3日先の4日分（`StatusController::PORT_BOARD_DAYS`）。トップの会社カードは今日の `operation_statuses`

---

## R1. どこで作るか（PHP か Python か）

**Decision**: Symfony の Console コマンド（`app:notify-irregular-statuses`）として PHP で作る。メールは Symfony Mailer で送る。

**Rationale**:
- FR-003（サイトの表示と判定を一致させる）。有効な会社・有効で direction のある航路だけを見る、no_service を便として数えない、などの表示ルールは PHP の Repository・Builder にある。Python に同じ判定を書き直すと、サイトを直したときにずれる
- Symfony Mailer は STARTTLS・証明書の検証・複数宛先・開発用の null トランスポートを標準で持つ。`MailerAssertionsTrait` でテストもしやすい
- スクレイパー（Constitution I）に通知の責務を混ぜずに済む。収集が失敗しても通知は動き、通知が失敗しても収集は止まらない（FR-008・SC-005）

**Alternatives considered**:
- スクレイパー（Python）の `schedule` に足す：常駐プロセスがすでにあり手軽だが、判定ロジックが二重になる。V1 の notifier をほぼ流用できる利点はあるが、V1 は証明書検証オフなのでそのままは使えない
- 収集の直後に送る（V1 の形）：V2 は 30 分ごとに取るので、確認時刻と収集の時刻が一致しない。spec の Assumptions どおり、収集とは切り離して確認時刻の最新状態を見る

## R2. 確認時刻にどう起動するか

**Decision**: 本番の app イメージに **supercronic** を入れ、supervisord のプログラムとして動かす。crontab は `docker/production/app/crontab` に置き、`0 1,6,15 * * *` で `bin/console app:notify-irregular-statuses` を www-data で動かす。タイムゾーンはイメージに `tzdata` を入れ、`TZ=Asia/Tokyo` にする。

**Rationale**:
- コマンドは 1 回ごとに起動して終わる。Doctrine の接続を持ち続けないので、MySQL の `wait_timeout`（既定 8 時間。15 時 → 翌 1 時は 10 時間空く）で「MySQL server has gone away」になる心配が無い
- supercronic はコンテナ向けの cron。**環境変数をそのまま子プロセスに渡す**（busybox の crond は渡さないので、`DATABASE_URL`・`MAILER_DSN` を別ファイルに書き出す細工が要る）。ログは標準出力に出るので `docker logs` で追える（既存の supervisord の方針と同じ）
- 時刻を逃した回はあとから実行しない（cron の性質）。FR-010 をそのまま満たす
- 設定がリポジトリとイメージの中で完結する。V1 のようにホストの crontab を手で触らない

**Alternatives considered**:
- Symfony Scheduler ＋ Messenger のワーカー：Symfony らしいが、`symfony/messenger`・`symfony/scheduler`・`dragonmantank/cron-expression` が増え、常駐ワーカーの接続切れ・メモリ・再起動の扱いが要る。再起動の瞬間に確認時刻が重なると取りこぼす。1 日 3 回のジョブには重い
- busybox crond（Alpine 標準）：追加のバイナリは要らないが、上のとおり環境変数が渡らない
- VPS のホストの crontab から `docker compose exec`（V1 と同じ）：手順が deploy/README の手作業になり、VPS を作り直したときに漏れる。コンテナが別名になると黙って止まる

**補足**:
- supercronic はリリースのバイナリを、**バージョンと SHA-1 を固定して** Dockerfile でダウンロードする（公式の手順どおり）。更新は Dependabot の対象外なので、`deploy/README.md` に確認の手順を書く
- 開発環境（`docker-compose.yml` の php コンテナ）では cron を動かさない。`make notify`・`make notify-dry-run` で手動で動かす（R7）

## R3. 二重送信を防ぐ（FR-009）

**Decision**: `notification_runs` テーブルに `(run_date, slot)` の一意キーを置く。コマンドは送る前に、その回の行を `INSERT` して回を確保する。一意キーに当たったら（すでに誰かが確保した）何もせずに終わる。送った・0 件・設定なし・失敗の結果は同じ行に `UPDATE` する。

**Rationale**:
- 確保（INSERT）が送信より先なので、2 つのプロセスが同時に動いても送るのは 1 つだけ。MySQL の一意制約で決まるのでロックの仕組みが要らない
- 送信の途中でプロセスが落ちたら、その回は `pending` のまま残り再送されない。「同じ回は 1 通まで」（FR-009）と「失敗した通知は次の確認時刻まで再送しない」（US3-2）を優先する
- 0 件の回・設定なしの回も行を残す。あとから「その回は動いたか」を確かめられる（US3 の「原因を追える記録」）

**Alternatives considered**:
- ファイルロック：コンテナを作り直すと消える。2 つのコンテナ（デプロイの入れ替え中）では効かない
- MySQL の `GET_LOCK()`：同時実行は防げるが、「同じ回にもう送った」は覚えられない（再起動直後の 2 回目を防げない）
- 送った後に記録する：送信と記録の間で落ちると、次の起動で同じ回をもう一度送る

**保持期間（Constitution III）**：運航状況の履歴ではなく、`scraper_logs` と同じ運用の記録。1 日 3 行で増え方は小さいが、使い道の無いまま貯めないよう、コマンドの最後に **90 日より古い行を消す**。

## R4. いつの実行を「その回」とみなすか（FR-001・FR-010）

**Decision**: コマンドは実行した時刻（日本時間）から回を決める。**1:00・6:00・15:00 のそれぞれから 10 分以内**ならその回。それ以外の時刻では「確認時刻ではない」と出して何もしない（終了コード 0）。手で動かすときは `--slot=1|6|15` で回を指定でき、そのときは時刻の窓を見ない（二重送信の確保は同じく行う）。

**Rationale**:
- cron は確認時刻ちょうどに起動するので、10 分の窓は起動の遅れ（コンテナの負荷・cron の誤差）の吸収だけ。SC-001（5 分以内に届く）とも矛盾しない
- 窓を外れた起動（再起動直後に誰かが手で動かした、など）が遅れて送らないようにする（FR-010）
- `--slot` は開発・障害時の手動確認用。指定した回も一意キーで確保するので、本番で誤って動かしても同じ回の 2 通目にはならない。ただし確認時刻より前に `--dry-run` 無しで動かすと、その回を先に確保してしまい、cron の本来の回は「処理済み」で送らない。テストや開発でいつでも動かせるよう時刻の制限はかけず、本番で手で動かすときは `--dry-run` を付ける運用にする（contracts/console-command.md・deploy/README.md に書く）

## R5. 「通常運航以外」の判定と対象（FR-002・FR-003・FR-012）

**Decision**:

| 項目 | 内容 |
|---|---|
| 対象の状態 | `cancelled`（欠航）・`delayed`（条件付・遅延）・`suspended`（運休）・`unknown`（不明） |
| 対象外 | `operating`（通常運航）・`no_service`（便無し）・`departure_statuses.status = null`（運航予定） |
| 日付 | 今日〜3 日先（サイトのボードと同じ 4 日分。`StatusController::PORT_BOARD_DAYS` を `PortBoardBuilder::DAYS` に移して共有する） |
| 会社・航路 | 有効な会社の有効な航路。`departure_statuses` はさらに direction のある航路（`findForBoard` と同じ） |
| 航路×日付 | `operation_statuses` の航路・日付ごとの最新 1 行（`findUpcomingByCompany` と同じく `MAX(scraped_at)`） |
| 港ごと | `departure_statuses` の行そのもの（キーごとに 1 行） |
| まとめ方 | (航路, 日付) をキーにまとめる。航路×日付が通常以外ならその状態を、通常以外の港があればその下に並べる |

**Rationale**:
- 「不明」はサイトでも「？ 不明」と出し、通常運航とは見せていないので V1 と同じく載せる（spec の Edge Cases）
- 寄港地変更・抜港は V2 では delayed・cancelled として入っている（#54）。値を新しく作らない
- 日付の範囲をサイトに合わせる。サイトに出ていない 5 日先以降の便を通知に載せると FR-003 に反する。スクレイパーの取得範囲（丸栄は 3 日先まで）とも合う
- `findForBoard` は 4 日分の全行（通常運航も含む）を取る。通知では状態で絞った専用のクエリを Repository に足す（行数は少ないが、毎回 Board を組み立てる必要は無い）

**既知の制約**：夜をまたぐ便は、途中の港の出港日が始発港の日付と変わる。キーは港ごとの「出港日」なので、その港は出港日の側に別の 1 件として載る。spec の「同じ便（同じ航路・同じ運航日）」の定義どおりで、V1 との比較（SC-004）でも V1 に載っている便が抜けることは無い。

## R6. 本文・件名の形（FR-005・FR-006）

**Decision**: Twig のテキストテンプレート（`templates/email/irregular_statuses.txt.twig`）で本文を作り、`Email::text()` で送る。件名は `【ShipInfo V2】非通常運航ステータスを検出 (N件)`。

```
以下の運航情報で通常運航以外のステータスが検出されました。

  会社名: マルエーフェリー
  運航日: 2026-10-07（水）
  方向　: 下り（那覇行き）
  状況　: 欠航
  備考　: 台風接近のため
  港　　:
    - 名瀬 07:00発 フェリーなみのうえ：欠航（台風接近のため）
    - 与論 13:10発 フェリーなみのうえ：欠航

  会社名: マリックスライン
  運航日: 2026-10-07（水）
  方向　: 上り（鹿児島行き）
  状況　: 通常運航（途中の港に変更あり）
  港　　:
    - 沖永良部 10:30発 クイーンコーラルクロス：欠航（抜港）
```

- 行頭・項目名は V1 と同じ（並べて比べやすくする。SC-004）
- 「方向」は `RouteDirectionEnum::label()`。direction の無い航路は航路名
- 航路×日付が通常運航（または情報が無い）で港だけ通常以外のときは、状況を「通常運航（途中の港に変更あり）」／「情報なし（途中の港に変更あり）」にする
- 状態の文言は `OperationStatusEnum::label()` を新しく作り、ステータスバッジ（`_status_badge.html.twig`）もそれを使うようにして、サイトと文言を一致させる（FR-003）
- 並びは会社（サイトと同じ会社 ID 順）→ 運航日 → 航路 ID → 港は寄港順（出港予定時刻順）
- 件数 N はまとめた後の (航路, 日付) の数

**Alternatives considered**:
- PHP で文字列を組み立てる：テンプレートのほうが本文の形を一目で見られ、変えやすい
- HTML メール：spec の範囲外（V1 と同じテキストのみ）

## R7. 設定と開発環境（FR-007・FR-008・FR-011）

**Decision**:

| 環境変数 | 内容 | 既定値 |
|---|---|---|
| `MAILER_DSN` | Symfony Mailer の DSN（例 `smtp://USER:PASS@smtp.example.com:587`） | `null://null` |
| `NOTIFY_FROM` | 送信元 | 空 |
| `NOTIFY_TO` | 宛先（カンマ区切り。空白・空要素は捨てる） | 空 |

- 3 つのどれかが空、または `MAILER_DSN` が `null://` のときは「設定が無いので送らなかった」と警告を出し、回の結果を `not_configured` にする
- 送信の例外（`TransportExceptionInterface`）は捕まえて、回の結果を `failed`・エラーの要約を保存し、エラーとして記録する。コマンドの終了コードは 1（supercronic のログで目立たせる）。どちらもスクレイパー・サイトには影響しない（別プロセス）
- `MAILER_DSN` の既定値は `services.yaml` の `parameters: env(MAILER_DSN): 'null://null'` に置く（本番イメージの `.env` は空なので）
- **TLS の証明書は検証する**（Symfony の既定）。V1 は検証をオフにしていたが、パスワードを平文同然で流すことになるので引き継がない。サーバーの証明書が通らないときは、まず DSN のホスト名を証明書の名前に合わせる。どうしても通らなければ `?verify_peer=0` を DSN に足せるが、`deploy/README.md` に理由を書くこと
- テスト環境：「設定なし」の判定は通知のサービスに注入した `%env(MAILER_DSN)%` で見る。Mailer 本体の DSN は `config/packages/mailer.yaml` の `when@test` で `null://null` に固定し、`phpunit.xml.dist` で `MAILER_DSN=smtp://mailer.test.invalid`・`NOTIFY_FROM`・`NOTIFY_TO` を入れる。これで「設定あり」の経路を通しつつ、実際には送らずに `MailerAssertionsTrait` で中身を確かめられる。「設定なし」「送信失敗」はサービスを直接組み立てる単体テスト（Mailer はモック）で確かめる
- 開発環境：`docker-compose.yml` に **Mailpit** を `tools` プロファイルで足し（`make up-tools` で起動、phpMyAdmin と同じ扱い）、php の `MAILER_DSN` を `smtp://mailpit:1025` にする。`make notify-dry-run` は送らずに件名・本文を出すだけ（回も確保しない）
- 本番：`compose.prod.yml` の app に 3 つを渡し、値は VPS の `.env.production` に V1 と同じ SMTP・宛先を入れる

**Alternatives considered**:
- V1 と同じ `SMTP_HOST` などの個別の変数：Symfony では DSN 1 本が標準。`SMTP_USER`・`SMTP_PASSWORD` は DSN の中で URL エンコードして入れる（手順を README に書く）
- Mailpit を既定で起動する：普段の開発でメールは使わないので、phpMyAdmin と同じくオプションにする

## R8. 依存の追加（Constitution の技術スタック）

**Decision**: `symfony/mailer`（7.4.*）だけを足す。Messenger は入れない（Mailer は Messenger が無ければ同期で送る）。supercronic は PHP の依存ではなく本番イメージのバイナリ。

**Rationale**: 技術スタック（PHP 8.3 + Symfony 7.4 + MySQL 8.0 + Docker Compose）の範囲内。Symfony 公式のコンポーネントで、新しい言語・フレームワークは増えない。
