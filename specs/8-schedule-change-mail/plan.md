# Implementation Plan: 運航に変更がある便をメールで知らせる（V1 と同じ時刻）

**Branch**: `8-schedule-change-mail` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

---

## Summary

日本時間の 1:00・6:00・15:00 に、今日〜3日先で通常運航以外（欠航・条件付・遅延・運休・不明）の便があれば、運営者へ `【ShipInfo V2】非通常運航ステータスを検出 (N件)` のテキストメールを 1 通送る。

- **作る場所**：Symfony の Console コマンド `app:notify-irregular-statuses`。サイトと同じ Repository・Enum で判定する（FR-003）。メールは Symfony Mailer
- **起動**：本番の app イメージに supercronic を入れ、supervisord から動かす（`0 1,6,15 * * *`、`TZ=Asia/Tokyo`）。1 回ごとに起動して終わるので、DB の接続を持ち続けない
- **二重送信の防止**：`notification_runs` の `(run_date, slot)` 一意キー。送る前に INSERT で回を確保する（FR-009）。確認時刻から 10 分を過ぎた起動は送らない（FR-010）
- **まとめ方**：`operation_statuses`（航路×日付）と `departure_statuses`（港ごと）を (航路, 日付) でまとめて 1 件にする（FR-012）
- **設定**：`MAILER_DSN`・`NOTIFY_FROM`・`NOTIFY_TO`。足りなければ警告を出して送らない。送信失敗は記録して終わる。どちらもスクレイパー・サイトには影響しない（FR-008）
- **開発**：`make notify-dry-run` で本文を見る。`make up-tools` で起動する Mailpit に送って確かめる（FR-011）

---

## Technical Context

**Language/Version**: PHP 8.3
**Primary Dependencies**: Symfony 7.4（Console・Mailer）、Twig（テキストのテンプレート）、Doctrine ORM 3。新しく `symfony/mailer` を足す。本番イメージに supercronic（バイナリ、バージョンと SHA-1 を固定）と `tzdata`
**Storage**: MySQL 8.0。`notification_runs` を新しく作る（マイグレーション）。既存のテーブルは読むだけ
**Testing**: PHPUnit（Repository は実 DB、まとめ方・本文は単体、コマンドは `CommandTester` ＋ `MailerAssertionsTrait`）
**Target Platform**: Docker Compose（開発）、さくら VPS の `compose.prod.yml`（本番）
**Project Type**: Web アプリ（MVP、Twig）＋ Console コマンド
**Performance Goals**: 1 回の確認でクエリ 3 本程度（最新の航路×日付・通常以外の港ごと・回の確保／更新）。数十行。SC-001（5 分以内に届く）は SMTP 次第で、処理自体は数秒
**Constraints**:
- サイトの表示と判定を一致させる（FR-003）。日付の範囲はボードと同じ 4 日分、対象の会社・航路も同じ条件
- 同じ回は 1 通まで（FR-009）。遅れて送らない（FR-010）
- 通知の失敗でスクレイパー・サイトを止めない（FR-008、SC-005）
- SMTP の TLS 証明書は検証する（V1 の検証オフは引き継がない）
- ログに DSN・パスワード・宛先アドレスを出さない
**Scale/Scope**: 1 日 3 回、宛先は運営者数名、1 通あたり数件〜数十件

未解決の NEEDS CLARIFICATION は無い（[research.md](research.md) で全部解決済み）。

---

## Constitution Check

| Gate | Status | 備考 |
|---|---|---|
| I. スクレイパー優先設計 | ✅ PASS | スクレイパーは変更しない。通知はスクレイパーの書いた行を読むだけで、収集と疎結合 |
| II. Twig + Controller、API なし | ✅ PASS | 画面・API は足さない。Console コマンドと Twig のテキストテンプレートだけ |
| III. データ品質・キーごとの最新状態 | ✅ PASS | 運航状況の履歴は持たない（確認時点の最新状態を読む）。`notification_runs` は `scraper_logs` と同じ運用の記録で、保持期間 90 日を決めて消す（research R3） |
| IV. Docker で完結 | ✅ PASS | supercronic は本番イメージに焼き込み、crontab もリポジトリに置く。開発は Mailpit を compose の `tools` プロファイルで足す。ホストの cron は使わない |
| V. フェーズごとにコミット・スコープを制限 | ✅ PASS | 下の PR1・PR2 に分け、tasks.md のグループごとにコミットする |
| 技術スタック（変更禁止） | ✅ PASS | Symfony 公式の `symfony/mailer` だけ。supercronic は PHP の依存ではなく、コンテナの cron の置き換え |

**Phase 1 設計の後に再チェック**: 違反は無し。

---

## Project Structure

### Documentation

```
specs/8-schedule-change-mail/
├── spec.md
├── research.md
├── data-model.md
├── contracts/
│   ├── console-command.md
│   └── notification-mail.md
├── quickstart.md
├── plan.md          ← このファイル
└── tasks.md         （/speckit.tasks で生成）
```

### 変更対象

```
app/composer.json・composer.lock・symfony.lock             # symfony/mailer
app/config/packages/mailer.yaml                          # 新規：dsn は %env(MAILER_DSN)%、when@test は null://null
app/config/services.yaml                                 # env(MAILER_DSN)・env(NOTIFY_FROM)・env(NOTIFY_TO) の既定値、通知サービスへの bind
app/phpunit.xml.dist                                     # テスト用の MAILER_DSN・NOTIFY_FROM・NOTIFY_TO

app/migrations/Version20261006000000.php                 # 新規：notification_runs
app/src/Entity/NotificationRun.php                       # 新規
app/src/Enum/NotificationResultEnum.php                  # 新規
app/src/Enum/OperationStatusEnum.php                     # label()・isIrregular()
app/src/Repository/NotificationRunRepository.php         # 新規：回の確保（INSERT、一意キー違反で false）・結果の更新・古い行の削除
app/src/Repository/OperationStatusRepository.php         # findLatestBetween()
app/src/Repository/DepartureStatusRepository.php         # findIrregularBetween()
app/src/View/IrregularService.php                        # 新規
app/src/View/IrregularPort.php                           # 新規
app/src/Service/IrregularServiceCollector.php            # 新規：2 つの Repository から (航路, 日付) でまとめる。DB 以外は純粋
app/src/Service/NotificationSlotResolver.php             # 新規：時刻 → 回（1・6・15、10 分の窓）
app/src/Service/IrregularStatusMailer.php                # 新規：設定の確認・件名と本文・送信・結果
app/src/Command/NotifyIrregularStatusesCommand.php       # 新規
app/src/Service/PortBoardBuilder.php                     # public const DAYS = 4（StatusController::PORT_BOARD_DAYS を移す）
app/src/Controller/StatusController.php                  # PortBoardBuilder::DAYS を使う
app/templates/email/irregular_statuses.txt.twig          # 新規
app/templates/status/_status_badge.html.twig             # 文言を status.label() に（見た目・文言は同じ）

app/tests/Repository/NotificationRunRepositoryTest.php   # 新規：確保・二重確保・古い行の削除
app/tests/Repository/OperationStatusRepositoryTest.php   # findLatestBetween
app/tests/Repository/DepartureStatusRepositoryTest.php   # findIrregularBetween
app/tests/Service/IrregularServiceCollectorTest.php      # 新規：まとめ方（contracts/notification-mail の例）
app/tests/Service/NotificationSlotResolverTest.php       # 新規：窓の内外・境目
app/tests/Service/IrregularStatusMailerTest.php          # 新規：設定なし・送信失敗・宛先の分解・件名
app/tests/Command/NotifyIrregularStatusesCommandTest.php # 新規：送る・0 件・処理済み・--dry-run・--slot の不正値

docker/production/app/Dockerfile                         # supercronic・tzdata・TZ=Asia/Tokyo、crontab のコピー
docker/production/app/crontab                            # 新規
docker/production/app/supervisord.conf                   # [program:supercronic]（user=www-data）
docker-compose.yml                                       # mailpit（tools プロファイル）、php に MAILER_DSN・NOTIFY_*
compose.prod.yml                                         # app に MAILER_DSN・NOTIFY_FROM・NOTIFY_TO
deploy/.env.production.example                           # 3 つを追加（空）
deploy/README.md                                         # 設定の入れ方（DSN の URL エンコード・証明書）、確認の仕方、supercronic の更新手順
scripts/verify-prod.sh                                   # supercronic が RUNNING・コンテナの TZ が Asia/Tokyo
Makefile                                                 # notify・notify-dry-run
CLAUDE.md                                                # よく使うコマンドに notify、重要な設計決定に通知の仕組みを1行
```

**Structure Decision**: 既存の Repository（取得）→ Service（組み立て・DB 非依存）→ View（表示用の値）の構成に合わせる。Console コマンドは `app/src/Command/` を新しく作る（Symfony の標準の置き場所）。メールの本文は画面と同じく Twig に置く。

---

## 実装の分割（PR）

| PR | 範囲 | spec | 主な変更 |
|---|---|---|---|
| **PR1** | 判定・まとめ方・本文・送信・回の確保（手動で動く） | US1・US2・US3（FR-002〜009・011・012） | `symfony/mailer`、`notification_runs`、Enum・Repository・View・Service・Command・テンプレート、テスト、`docker-compose.yml` の Mailpit、Makefile |
| **PR2** | 確認時刻の自動起動・本番の設定 | FR-001・FR-010（起動側）、FR-007（本番） | Dockerfile（supercronic・tzdata）、crontab、supervisord、`compose.prod.yml`・`.env.production.example`・`deploy/README.md`、verify-prod、CLAUDE.md |

PR1 だけを本番に出しても、cron が無いので何も送らない（安全）。PR2 の前に VPS の `.env.production` に 3 つの設定を入れておけば、PR2 のデプロイ後の最初の確認時刻から届く。入れていなければ `not_configured` の警告が出るだけ。

---

## 主な設計判断（詳細は research.md）

| 判断 | 内容 | research |
|---|---|---|
| 作る場所 | PHP の Console コマンド ＋ Symfony Mailer。サイトと同じ判定を使う | R1 |
| 起動 | 本番イメージの supercronic（環境変数をそのまま渡す・遅れて実行しない）。常駐ワーカーは作らない | R2 |
| 二重送信 | `notification_runs (run_date, slot)` の一意キー。送る前に確保 | R3 |
| 回の決め方 | 確認時刻から 10 分以内。`--slot` で手動指定（窓は見ないが確保は同じ） | R4 |
| 対象 | cancelled・delayed・suspended・unknown。今日〜3 日先。有効な会社・航路 | R5 |
| まとめ方 | (航路, 日付)。港だけ通常以外なら「通常運航（途中の港に変更あり）」 | R5・R6 |
| 本文 | V1 と同じ項目名のテキスト。Twig テンプレート。状態の文言は `OperationStatusEnum::label()` をサイトと共有 | R6 |
| 設定 | `MAILER_DSN`・`NOTIFY_FROM`・`NOTIFY_TO`。TLS 証明書は検証する | R7 |
| 依存 | `symfony/mailer` だけ。Messenger・Scheduler は入れない | R8 |

## Complexity Tracking

違反は無いので記載なし。
