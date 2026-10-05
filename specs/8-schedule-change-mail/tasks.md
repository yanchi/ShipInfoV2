# Tasks: 運航に変更がある便をメールで知らせる（V1 と同じ時刻）

**Input**: Design documents from `specs/8-schedule-change-mail/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/console-command.md, contracts/notification-mail.md, quickstart.md

**Tests**: 入れる。plan.md の「変更対象」でテストファイル（Repository・Service・Command）を明示していて、FR-009（二重送信なし）・FR-003（サイトと判定が一致）・FR-008（失敗しても止まらない）はテストでしか確かめにくいため。

**Story ラベル**: spec.md の User Story 番号（US1〜US3）。確認時刻の自動起動（PR2）は US1 の FR-001・FR-010 なので [US1] を付ける。

**PR の分け方**（plan.md「実装の分割」）: 2 つの PR に分け、順番にマージする。

| PR | ブランチ | Phase | spec |
|---|---|---|---|
| PR1 | `8-schedule-change-mail`（今のブランチ。spec・plan のコミットを含む） | Phase 1〜5 | US1〜US3（FR-002〜009・011・012）。手動の `bin/console` で動く |
| PR2 | `8-schedule-change-mail-cron`（PR1 のマージ後に `master` から切る） | Phase 6〜7 | US1 の FR-001・FR-010（起動側）、FR-007（本番の設定）、仕上げ |

PR1 だけを本番に出しても cron が無いので何も送らない（安全）。

**コミット**: 各 Phase の Checkpoint でコミットする（constitution V）。

**共通の注意**:
- 既存の `operation_statuses`・`departure_statuses` は読むだけ。スクレイパー（`scraper/`）・`01_schema.sql`・`scraper/scraper/db/models.py` は触らない（data-model §1）
- 「今日」は `new \DateTimeImmutable('today')`（PHP の `date.timezone = Asia/Tokyo` は開発・本番とも設定済み。既存の StatusController と同じ）
- ログ・`error_message` に DSN・パスワード・宛先のアドレスを出さない（宛先は件数だけ。contracts/console-command.md「出力」）
- 文言（件名・本文・ログ）は contracts/ から写す。勝手に言い換えない
- 各 Phase の終わりに `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` が通ること

---

# PR1: 判定・まとめ方・本文・送信・回の確保（`8-schedule-change-mail`）

## Phase 1: Setup

- [ ] T001 `8-schedule-change-mail` ブランチで `make up` → `make test-php` が全部通ることを確認してから始める
- [ ] T002 php コンテナで `composer require symfony/mailer:7.4.*` を実行し、`app/composer.json`・`app/composer.lock`・`app/symfony.lock` を更新する（research R8。Messenger・Scheduler は入れない）
  - Flex のレシピが作った `app/config/packages/mailer.yaml` を `framework.mailer.dsn: '%env(MAILER_DSN)%'` にし、`when@test:` で `framework.mailer.dsn: 'null://null'` に固定する（research R7）
  - レシピが `app/compose.yaml`・`app/compose.override.yaml` に足した mailer のサービスは戻す（このリポジトリはルートの `docker-compose.yml` を使う）。`app/.env` に足された `MAILER_DSN=null://null` の行は残してよい
- [ ] T003 [P] `app/config/services.yaml` の `parameters:` に既定値を足す：`env(MAILER_DSN): 'null://null'`・`env(NOTIFY_FROM): ''`・`env(NOTIFY_TO): ''`（本番イメージの `.env` は空なので、未設定でもコンテナが起動するように。research R7）
- [ ] T004 [P] `app/phpunit.xml.dist` の `<php>` に `<server name="MAILER_DSN" value="smtp://mailer.test.invalid" force="true" />`・`NOTIFY_FROM`（`noreply@example.com`）・`NOTIFY_TO`（`ops1@example.com, ,ops2@example.com`）を足す。Mailer 本体は `when@test` で `null://null` なので実際には送らず、通知サービスからは「設定あり」に見える（research R7）
- [ ] T005 [P] `docker-compose.yml` に Mailpit を足す（FR-011、research R7）
  - `mailpit:` サービス：`image: axllent/mailpit:<タグ>`（実装のときに Docker Hub の最新の安定版のタグを確かめて固定する。`latest` にはしない）、`ports: "8025:8025"`、`networks: [shipinfo]`、`profiles: [tools]`（phpMyAdmin と同じ扱い）
  - php の `environment` に `MAILER_DSN: "${MAILER_DSN:-smtp://mailpit:1025}"`・`NOTIFY_FROM: "${NOTIFY_FROM:-shipinfo-v2@localhost}"`・`NOTIFY_TO: "${NOTIFY_TO:-ops@localhost}"`
- [ ] T006 [P] `Makefile` に `notify-dry-run`（`bin/console app:notify-irregular-statuses --slot=6 --dry-run`）と `notify`（`SLOT ?= 6` で `--slot=$(SLOT)`）を足す。既存のターゲットと同じく php コンテナで `exec` し、`.PHONY` と `## ` のヘルプも付ける。`help` の末尾の phpMyAdmin の行の下に `Mailpit: make up-tools && open http://localhost:8025` を足す（contracts/console-command.md「Make」）

**Checkpoint**: `make up` が通り、`make up-tools` で Mailpit が `http://localhost:8025` で開く。`make test-php`・`make lint-php` が通る → コミット

---

## Phase 2: Foundational（ブロッキング前提）

**Purpose**: どの US も使う「状態の判定・文言」「日付の範囲」「回の記録」を先に作る

**⚠️ CRITICAL**: この Phase が終わるまで US の実装を始めないこと

- [ ] T007 [P] `app/src/Enum/OperationStatusEnum.php` に `label(): string`（data-model §3 の表：通常運航・条件付・遅延・欠航・運休・不明・便なし）と `isIrregular(): bool`（Delayed・Cancelled・Suspended・Unknown で true）を足す。`/** @return list<self> */ public static function irregularCases(): array` も足し、Repository の `IN` 条件はこれから作る（判定を 1 か所に集める）
- [ ] T008 [P] `app/tests/Enum/OperationStatusEnumTest.php` を新しく作り、6 つの値すべての `label()` と `isIrregular()`、`irregularCases()` が `isIrregular()` が true のものと一致することを確かめる
- [ ] T009 `app/templates/status/_status_badge.html.twig` で、operating・delayed・cancelled・suspended・unknown の各分岐の文言を `{{ status.label() }}` にする（`✓ {{ status.label() }}` のように記号は残す。クラス・分岐の順番・no_service の行は変えない。T007 の後）。画面の文言は今と同じなので `app/tests/Controller/StatusControllerTest.php` は変えずに通ること（FR-003、research R6）
- [ ] T010 [P] `app/src/Service/PortBoardBuilder.php` に `public const DAYS = 4;` を足し、`app/src/Controller/StatusController.php` の `PORT_BOARD_DAYS` を消して `PortBoardBuilder::DAYS` を使う（research R5。振る舞いは変えない）
- [ ] T011 [P] `app/src/Enum/NotificationResultEnum.php` を新しく作る：`Pending = 'pending'`・`Sent = 'sent'`・`None = 'none'`・`NotConfigured = 'not_configured'`・`Failed = 'failed'`（data-model §1）
- [ ] T012 `app/src/Entity/NotificationRun.php` を新しく作る（T011 の後。data-model §1 の列・型どおり）
  - `#[ORM\Table(name: 'notification_runs')]`、`#[ORM\UniqueConstraint(name: 'uniq_notification_run', columns: ['run_date', 'slot'])]`、`repositoryClass: NotificationRunRepository::class`
  - `id`（unsigned）・`runDate`（`date_immutable`）・`slot`（`smallint` unsigned。MySQL では TINYINT にしたいのでマイグレーション側で型を合わせ、`schema:validate` が通る組み合わせにする）・`result`（`enumType: NotificationResultEnum`, length 32）・`itemCount`（unsigned int）・`errorMessage`（text, nullable）・`createdAt`・`updatedAt`
  - 時刻は `app/src/Entity/ScraperLog.php` と同じく `#[ORM\HasLifecycleCallbacks]` の `PrePersist`・`PreUpdate` で入れる
- [ ] T013 `app/migrations/Version20261006000000.php` を新しく作り、`notification_runs` を作る（T012 の後）。列・NULL・一意キー `uniq_notification_run (run_date, slot)` は data-model §1 のとおり。`down()` で DROP。`make migrate` のあと `make lint-php`（`doctrine:schema:validate`）が通ること
- [ ] T014 `app/src/Repository/NotificationRunRepository.php` を新しく作る（T013 の後。research R3）
  - `claim(\DateTimeImmutable $runDate, int $slot): bool`：DBAL の `Connection::insert('notification_runs', …)` で `result = pending`・`item_count = 0` の行を入れて true。`UniqueConstraintViolationException` を捕まえたら false（ORM の `flush()` で例外を出すと EntityManager が閉じるので、確保だけは DBAL で行う）
  - `finish(\DateTimeImmutable $runDate, int $slot, NotificationResultEnum $result, int $itemCount, ?string $errorMessage): void`：`result = 'pending'` の行だけを `UPDATE` する（pending 以外は書き換えない。data-model §1「状態の遷移」）。`updated_at` も更新する
  - `deleteOlderThan(\DateTimeImmutable $date): int`：`run_date < :date` の行を消し、消した行数を返す
- [ ] T015 `app/tests/Repository/NotificationRunRepositoryTest.php` を新しく作る（T014 の後）：初回の `claim` が true・同じ (日付, 回) の 2 回目が false・別の回は true、`finish` で pending → sent になり、sent の行にもう一度 `finish(failed)` しても sent のまま、`deleteOlderThan` で 91 日前の行だけ消えて 90 日前の行は残る。テストで作った行は `tearDown` で消す（既存の Repository テストのやり方に合わせる）

**Checkpoint**: `notification_runs` がマイグレーションで作られ、回の確保が一意キーで 1 回だけ成功する。バッジの文言は変わらない。全テスト・phpstan・lint が通る → コミット

---

## Phase 3: User Story 1 - 決まった時刻に運航の変更をメールで知る (Priority: P1) 🎯 MVP

**Goal**: `bin/console app:notify-irregular-statuses --slot=6` を動かすと、今日〜3 日先の通常運航以外の便を (航路, 日付) でまとめて 1 通のテキストメールにして送り、同じ回は 2 通目を送らない

**Independent Test**: 欠航・遅延の便があるデータで `make notify SLOT=6` → Mailpit に 1 通届き本文にその便が載る。もう一度動かすと「処理済み」で届かない。通常運航だけのデータでは何も届かない。`make test-php` で T016〜T021 が通る

### Tests for User Story 1

> **NOTE: 先に書いて、実装前に FAIL することを確認する**

- [ ] T016 [P] [US1] `app/tests/Repository/OperationStatusRepositoryTest.php` に `findLatestBetween` のテストを足す：同じ航路・日付に `scraped_at` の違う 2 行があると新しい方だけ返る、昨日と 4 日先は返らない、無効な会社・無効な航路の行は返らない、通常運航の行も返る（状態で絞らない。data-model §3）
- [ ] T017 [P] [US1] `app/tests/Repository/DepartureStatusRepositoryTest.php` に `findIrregularBetween` のテストを足す：cancelled・delayed・suspended・unknown は返る、operating・no_service・status null は返らない、昨日・4 日先・無効な会社・無効な航路・direction の無い航路は返らない
- [ ] T018 [P] [US1] `app/tests/Service/IrregularServiceCollectorTest.php` を新しく作る（DB を使わない単体テスト。エンティティを `new` して組み立てる）。contracts/notification-mail.md「テストで押さえる例」の まとめ方の行をすべて押さえる
  - 航路×日付が欠航・港なし → 1 件、`statusText()` が `欠航`、`detail()` が備考
  - 同じ航路・日付で航路×日付が欠航・港 2 つが欠航 → 1 件で `ports` が 2 つ（出港予定時刻順、時刻なしは最後）
  - 航路×日付は通常運航・港 1 つだけ欠航 → 1 件、`通常運航（途中の港に変更あり）`、`detail()` は null
  - 航路×日付の行が無い・no_service で港だけ欠航 → `情報なし（途中の港に変更あり）`
  - すべて通常運航・便なし → 0 件
  - unknown → `不明`、suspended → `運休`
  - 並びが会社 ID → 日付 → 航路 ID
  - `directionLabel()` が direction のある航路は `RouteDirectionEnum::label()`、無い航路は航路名
- [ ] T019 [P] [US1] `app/tests/Service/NotificationSlotResolverTest.php` を新しく作る（research R4）：`01:00`・`01:09:59` → 1、`01:10:00` → null、`00:59` → null、`06:05` → 6、`15:00` → 15、`03:12` → null。`fromOption('1'|'6'|'15')` は int を返し、`'0'`・`'7'`・`'abc'`・`''` は `\InvalidArgumentException`
- [ ] T020 [P] [US1] `app/tests/Service/IrregularStatusMailerTest.php` を新しく作る（Mailer は `MailerInterface` のモック。設定ありの経路だけ。US3 の経路は T033 で足す）：送った `Email` の From・To（`NOTIFY_TO=" a@example.com, ,b@example.com "` → 2 つ）・件名 `【ShipInfo V2】非通常運航ステータスを検出 (2件)`・HTML パートが無いこと・本文に会社名・`運航日: 2026-10-07（水）` の形・`方向　:`・`状況　:`・`港　　:` の下の `    - 名瀬 07:00発 フェリーなみのうえ：欠航（台風接近のため）` の形の行があること（contracts/notification-mail.md「本文」）。戻り値の `NotificationOutcome` の `result` が `Sent`
- [ ] T021 [US1] `app/tests/Command/NotifyIrregularStatusesCommandTest.php` を新しく作る（`KernelTestCase` ＋ `CommandTester` ＋ `MailerAssertionsTrait`。実 DB に今日の欠航の `operation_statuses` を作る。テストで作った行と今日の `notification_runs` は `tearDown` で消す）
  - **テスト DB の既存の行に依存しない**：`setUp` で、今日〜3 日先の `operation_statuses`・`departure_statuses` と今日の `notification_runs` を消してから、テストに要る行だけを作る（テスト DB は `_test` の別 DB なので消してよい。seed の会社・航路・港は消さない）。件数・`none` の判定がほかのテストの消し忘れや seed で変わらないようにする
  - `--slot=6` → 終了コード 0、`assertEmailCount(1)`、件名・本文に作った便、`notification_runs` の今日の 6 時の行が `sent`・`item_count` が件数
  - 同じ `--slot=6` を 2 回 → 2 回目は `この回は処理済みです` を含む出力で、メールは増えない（FR-009）
  - 欠航の行を作らない（通常運航だけ）→ 終了コード 0、メール 0 通、結果 `none`（FR-002・SC-002）
  - `--slot=6 --dry-run` → 出力に件名と本文、メール 0 通、`notification_runs` に行ができない
  - `--slot=7` → 終了コード 2

### Implementation for User Story 1

- [ ] T022 [P] [US1] `app/src/Repository/OperationStatusRepository.php` に `findLatestBetween(\DateTimeImmutable $from, int $days): array`（`@return list<OperationStatus>`）を足す（data-model §3）。`findUpcomingByCompany` と同じく (航路, 日付) ごとの `MAX(scraped_at)` の行を取り、航路・会社を JOIN して `r.active`・`fc.active` で絞る。状態では絞らない
- [ ] T023 [P] [US1] `app/src/Repository/DepartureStatusRepository.php` に `findIrregularBetween(\DateTimeImmutable $from, int $days): array`（`@return list<DepartureStatus>`）を足す。`findForBoard` と同じ JOIN・範囲・条件に `d.status IN (:statuses)`（`OperationStatusEnum::irregularCases()`）を足す
- [ ] T024 [P] [US1] `app/src/View/IrregularPort.php` を新しく作る（data-model §2。`final readonly` のプロパティ：`portName`・`shipName`（空文字は null）・`departureAt`・`status`・`detail`）
- [ ] T025 [US1] `app/src/View/IrregularService.php` を新しく作る（T024 の後。data-model §2）：`company`・`route`・`date`・`routeStatus`・`ports` と、`isRouteIrregular()`・`directionLabel()`・`statusText()`・`detail()`。`statusText()` の文言は contracts/notification-mail.md「状況の文言」の表のとおり
- [ ] T026 [US1] `app/src/Service/IrregularServiceCollector.php` を新しく作る（T022〜T025 の後。research R5）
  - `collect(\DateTimeImmutable $today): array`（`@return list<IrregularService>`）：`findLatestBetween($today, PortBoardBuilder::DAYS)` と `findIrregularBetween($today, PortBoardBuilder::DAYS)` を読み、`build()` に渡す
  - `build(array $operationStatuses, array $departureStatuses): array`：DB を使わない純粋なメソッド（T018 はこれを呼ぶ）。キーは `routeId|Y-m-d`。航路×日付が `isIrregular()` か、通常以外の港がある (航路, 日付) だけを `IrregularService` にする。並びは会社 ID → 日付 → 航路 ID、港は出港予定時刻順（時刻なしは最後）
- [ ] T027 [P] [US1] `app/src/Service/NotificationSlotResolver.php` を新しく作る（research R4）：`public const SLOTS = [1, 6, 15]`・`WINDOW_MINUTES = 10`、`resolve(\DateTimeImmutable $now): ?int`（その日の各時刻から 10 分未満ならその回）、`fromOption(string $value): int`（不正値は `\InvalidArgumentException`）
- [ ] T028 [P] [US1] `app/templates/email/irregular_statuses.txt.twig` を新しく作る（contracts/notification-mail.md「本文」の形をそのまま。research R6 の例と 1 文字ずつ同じになること）。曜日は `['日','月','火','水','木','金','土'][date.format('w')]` で出す。テキストなので `{% autoescape false %}` で囲む（`&` などがエスケープされないように）
- [ ] T029 [US1] `app/src/Service/IrregularStatusMailer.php` を新しく作る（T028 の後。research R6・R7）
  - コンストラクタ：`MailerInterface`・`Twig\Environment`・`#[Autowire(env: 'MAILER_DSN')] string $mailerDsn`・`#[Autowire(env: 'NOTIFY_FROM')] string $from`・`#[Autowire(env: 'NOTIFY_TO')] string $to`（または `services.yaml` の `bind`。どちらか 1 つに揃える）
  - `public const SUBJECT_PREFIX = '【ShipInfo V2】';`、`subject(int $count): string` → `【ShipInfo V2】非通常運航ステータスを検出 (N件)`、`body(list<IrregularService> $items): string`（テンプレートを描画）
  - `recipients(): list<string>`：`NOTIFY_TO` をカンマで分け、前後の空白を除き、空を捨てる
  - `send(list<IrregularService> $items): NotificationOutcome`：`Email` を `from`・`to(...recipients)`・`subject`・`text(body)` で作って送り、`result = Sent` を返す（設定なし・失敗の分岐は US3 の T034 で足す）
  - `app/src/View/NotificationOutcome.php` を新しく作る：`final readonly` で `result`（`NotificationResultEnum`）・`errorSummary`（`?string`）・`missingSettings`（`list<string>`）
- [ ] T030 [US1] `app/src/Command/NotifyIrregularStatusesCommand.php` を新しく作る（T014・T026・T027・T029 の後。contracts/console-command.md「処理の順番」1〜4・6・8）
  - `#[AsCommand(name: 'app:notify-irregular-statuses', description: '運航に変更がある便をメールで知らせる')]`、オプション `--slot`（値必須）・`--dry-run`
  - `--slot` が不正 → エラーを出して `Command::INVALID`（2）。`--slot` 無し → `NotificationSlotResolver::resolve(new \DateTimeImmutable('now'))`、null なら `確認時刻ではありません（現在 HH:MM）` を出して 0
  - `--dry-run`：集めて件名と本文を出すだけ（確保しない・送らない・消さない）。0 件なら 0 件の文言を出す
  - それ以外：`claim()` が false → `Y-m-d N時の回は処理済みです` で 0。集めて 0 件 → `finish(None)`・`Y-m-d N時：通常運航以外の便はありません`。1 件以上 → `send()` → `finish(Sent, 件数)`・`Y-m-d N時：N件を送りました（宛先 M）`
  - 最後に `deleteOlderThan(今日 - 90 日)`（research R3）
  - 出力は `SymfonyStyle`（info は `writeln`/`success`、warning は `warning`、error は `error`）で、contracts/console-command.md「出力」の文言どおり
- [ ] T031 [US1] `make test-php`・`make phpstan`・`make cs-php`・`make lint-php` を通す（T016〜T021 が通る）。そのあと quickstart.md「開発環境で中身を見る」「開発環境で送ってみる」を手で確かめる（`make notify-dry-run`、`make up-tools` → `make notify SLOT=6` → Mailpit に 1 通、もう一度で「処理済み」）

**Checkpoint**: 手動の `--slot` で、まとめた 1 通が届き、同じ回は 2 通目が届かない。US1 の Acceptance Scenarios 1〜4 を満たす（5 の「確認時刻以外は送らない」はコマンド側の窓まで。自動起動は PR2）→ コミット

---

## Phase 4: User Story 2 - V1 と V2 のメールを見分けられる (Priority: P1)

**Goal**: V2 の件名が必ず `【ShipInfo V2】` で始まり、V1 の `【ShipInfo】` と前方一致しない

**Independent Test**: `make test-php` で T032 が通る。Mailpit で件名が `【ShipInfo V2】` で始まる

- [ ] T032 [US2] `app/tests/Service/IrregularStatusMailerTest.php` に、件名が `IrregularStatusMailer::SUBJECT_PREFIX`（`【ShipInfo V2】`）で始まり、`str_starts_with($subject, '【ShipInfo】')` が false であることを、件数 1・3・10 で確かめるテストを足す（contracts/notification-mail.md「ヘッダー」、SC-006）。`app/tests/Command/NotifyIrregularStatusesCommandTest.php` の送信のテストでも、実際に送られた `Email` の件名が `【ShipInfo V2】` で始まることを確かめる

**Checkpoint**: 件名で V1 と見分けられることがテストで固定される → コミット

---

## Phase 5: User Story 3 - メールの設定が無い・送れなくても運航情報の収集は止まらない (Priority: P2)

**Goal**: 設定が足りなければ警告を出して `not_configured`、送信で例外なら記録して `failed`・終了コード 1。どちらも同じ回を再送しない

**Independent Test**: quickstart.md「設定なし・送信失敗を確かめる」の 2 つのコマンドで警告・エラーが出て、`notification_runs` の結果がそれぞれ `not_configured`・`failed`。`make test-php` で T033 が通る

### Tests for User Story 3

- [ ] T033 [US3] `app/tests/Service/IrregularStatusMailerTest.php` に足す（Mailer はモック）
  - `MAILER_DSN` が空・`null://null`、`NOTIFY_FROM` が空、`NOTIFY_TO` が空・`" , "` のそれぞれ → `NotConfigured` を返し、Mailer の `send` が呼ばれない。警告の文言に足りない設定の名前（`NOTIFY_TO` など）が入り、DSN の値は入らない
  - Mailer の `send` が `TransportException('Connection refused')` を投げる → `Failed` を返し、エラーの要約が取れる。要約に DSN のユーザー名・パスワード（`smtp://user:secret@…` の `secret`）が入らない
  - コマンドのテスト（`app/tests/Command/NotifyIrregularStatusesCommandTest.php`）に、`IrregularStatusMailer` を `static::getContainer()->set()` で失敗するものに差し替えて `--slot=15` → 終了コード 1、結果 `failed`、もう一度動かすと「処理済み」で再送しないテストを足す（US3-2）

### Implementation for User Story 3

- [ ] T034 [US3] `app/src/Service/IrregularStatusMailer.php` の `send()` に分岐を足す（research R7）
  - 送る前に設定を確かめる：`MAILER_DSN` が空か `null://` で始まる、`NOTIFY_FROM` が空、`recipients()` が空 → `NotificationOutcome` の `result = NotConfigured`・`missingSettings` に足りない設定の名前（`MAILER_DSN`・`NOTIFY_FROM`・`NOTIFY_TO`）
  - `TransportExceptionInterface` を捕まえて `result = Failed`・`errorSummary`。要約は例外のメッセージから作り、DSN（`MAILER_DSN` の値・`user:pass@` の部分）を伏せる。長さは 1000 文字までに切る
- [ ] T035 [US3] `app/src/Command/NotifyIrregularStatusesCommand.php` に contracts/console-command.md「処理の順番」5・7 を足す：`NotConfigured` → `{設定名} が未設定のためメールを送りませんでした` を warning で出し、`finish(NotConfigured, 0)`・終了コード 0。`Failed` → `メールの送信に失敗しました: {要約}` を error で出し、`finish(Failed, 0, 要約)`・終了コード 1。どちらでも最後の `deleteOlderThan` は動かす
- [ ] T036 [US3] `make test-php`・`make phpstan`・`make cs-php` を通す。quickstart.md「設定なし・送信失敗を確かめる」の 2 つのコマンドを動かし、そのあと `make scraper-run` とトップページが普段どおり動くことを確かめる（SC-005）

**Checkpoint**: 設定なし・送信失敗でも記録が残り、再送しない。US3 の Acceptance Scenarios 1・2 を満たす → コミット → PR1 を作る（PR の本文に「cron は PR2。PR1 だけでは自動で送らない」と書く）

---

# PR2: 確認時刻の自動起動・本番の設定（`8-schedule-change-mail-cron`）

> PR1 のマージ後に `master` から `8-schedule-change-mail-cron` を切る。マージ前に VPS の `.env.production` に `MAILER_DSN`・`NOTIFY_FROM`・`NOTIFY_TO` を入れておく（入れていなければ `not_configured` の警告が出るだけ）

## Phase 6: User Story 1（続き）- 確認時刻に自動で動く (Priority: P1)

**Goal**: 本番の app コンテナで、日本時間の 1:00・6:00・15:00 にコマンドが www-data で動く（FR-001・FR-010）

**Independent Test**: `make verify-prod` で supercronic が RUNNING、コンテナの TZ が Asia/Tokyo、crontab の構文が通る。デプロイ後の最初の確認時刻のあと、`notification_runs` にその回の行がある

- [ ] T037 [P] [US1] `docker/production/app/crontab` を新しく作る（contracts/console-command.md「起動（本番）」のコメントと行をそのまま。末尾は改行で終える）
- [ ] T038 [US1] `docker/production/app/Dockerfile` の runtime ステージを直す（research R2）
  - `apk add` に `tzdata` を足し、`ENV` に `TZ=Asia/Tokyo` を足す
  - supercronic を公式のリリース（github.com/aptible/supercronic/releases）から入れる。実装のときに最新のリリースのページを開き、`ARG SUPERCRONIC_VERSION`（例 `v0.2.33` の形）と、その版の `supercronic-linux-amd64` の `ARG SUPERCRONIC_SHA1SUM` を書き写す（推測で書かない）。CI のイメージのビルドは platforms の指定が無く amd64 だけなので、amd64 のバイナリだけを入れる（arm64 は対応しない）
  - `curl -fsSLO` → `echo "${SUPERCRONIC_SHA1SUM}  supercronic-linux-amd64" | sha1sum -c -` → `/usr/local/bin/supercronic` に置いて `chmod +x`。curl が無ければ `--virtual` でビルドのときだけ入れて消す
  - `COPY docker/production/app/crontab /etc/crontab`
- [ ] T039 [US1] `docker/production/app/supervisord.conf` に `[program:supercronic]` を足す（T038 の後）：`command=supercronic /etc/crontab`・`user=www-data`・`autostart=true`・`autorestart=true`・`priority=30`、標準出力・標準エラーは既存のプログラムと同じく `/dev/stdout`・`/dev/stderr`（`maxbytes=0`）。冒頭のコメントに「supercronic で通知のコマンドを動かす」を足す
- [ ] T040 [US1] `compose.prod.yml` の app の `environment` に `MAILER_DSN: ${MAILER_DSN:-null://null}`・`NOTIFY_FROM: ${NOTIFY_FROM:-}`・`NOTIFY_TO: ${NOTIFY_TO:-}` を足す（必須にしない。FR-008）。`deploy/.env.production.example` に 3 つを空で足し、URL エンコードの注意をコメントで書く（quickstart.md「本番に出すとき」1）。**PR2 をマージする前に**、quickstart.md「本番に出すとき」2 のとおり VPS の app コンテナから本番の SMTP で自分宛てに 1 通送り、証明書の検証で落ちないことを確かめる（V1 は検証オフだったので。落ちたら T042 の証明書の節に沿って直してからマージする）
- [ ] T041 [US1] `scripts/verify-prod.sh` に確認を足す（既存の `section`・`ok` の書き方に合わせる）
  - `supervisorctl status supercronic` が `RUNNING`
  - app コンテナの `date +%Z` が `JST`（TZ）
  - `supercronic -test /etc/crontab` が成功する
  - `bin/console app:notify-irregular-statuses --slot=6 --dry-run` が終了コード 0（本番イメージで Mailer・テンプレートが読めること）

**Checkpoint**: `make verify-prod` が通る。US1 の Acceptance Scenario 5（確認時刻以外は送らない）と FR-001・FR-010 を満たす → コミット

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T042 [P] `deploy/README.md` に通知の節を足す：`.env.production` への 3 つの入れ方（DSN のユーザー名・パスワードの URL エンコード）、TLS の証明書は検証すること（通らないときはまずホスト名を合わせる。`verify_peer=0` を使うなら理由を書く。research R7）、確認の仕方（quickstart.md「本番に出すとき」4 のコマンド。`result = 'pending'` が残っている回は送信の途中で落ちた回）、本番で手で動かすときは必ず `--dry-run` を付けること（付けないと確認時刻より前ならその回を先に取ってしまう。research R4）、supercronic の更新手順（Dependabot の対象外なので、リリースのページでバージョンと SHA-1 を確かめて Dockerfile の `ARG` を直す。research R2）
- [ ] T043 [P] `CLAUDE.md` の「よく使うコマンド」に `make notify-dry-run`・`make notify SLOT=6` を、「重要な設計決定」に「運航に変更がある便の通知は app コンテナの supercronic が 1・6・15 時に `app:notify-irregular-statuses` を動かす。同じ回は `notification_runs` の一意キーで 1 通まで」を 1 行で足す
- [ ] T044 `make test-php`・`make phpstan`・`make cs-php`・`make lint-php`・`make audit`・`make verify-prod` を全部通す → コミット → PR2 を作る
- [ ] T045 デプロイ後、quickstart.md「本番に出すとき」4 のコマンドで最初の確認時刻の結果を確かめ、並行運用の 1 週間、V1 と V2 の同じ回のメールを比べる（SC-004。V1 は 0 時、V2 は 1 時）

---

## Dependencies & Execution Order

### Phase の順番

```
Phase 1 Setup ─▶ Phase 2 Foundational ─▶ Phase 3 US1 ─┬─▶ Phase 4 US2 ─┐
                                                       └─▶ Phase 5 US3 ─┴─▶ PR1 マージ ─▶ Phase 6 US1（起動）─▶ Phase 7
```

- **US1（Phase 3）** は Phase 2 の後。MVP の本体
- **US2（Phase 4）** は T029（件名）の後ならいつでも。テストを足すだけ
- **US3（Phase 5）** は T029・T030 の後（同じファイルに分岐を足す）。US2 とは別ファイルの部分は並べられるが、どちらも `IrregularStatusMailerTest.php` を触るので順番に進めるのが安全
- **Phase 6** は PR1 のマージ後（別ブランチ）

### タスクの依存（主なもの）

- T007 → T009（バッジは `label()` を使う）、T023（`irregularCases()`）、T025・T026（`isIrregular()`）
- T011 → T012 → T013 → T014 → T015
- T010 → T026（`PortBoardBuilder::DAYS`）
- T022・T023・T024 → T025 → T026
- T028 → T029 → T030、T014・T026・T027 → T030
- T029・T030 → T034・T035
- T038 → T039・T041

### Parallel Opportunities

- Phase 1：T003・T004・T005・T006（別ファイル）
- Phase 2：T007・T008・T010・T011（別ファイル）
- Phase 3 のテスト：T016〜T020（別ファイル）
- Phase 3 の実装：T022・T023・T024・T027・T028（別ファイル）
- Phase 7：T042・T043

### Parallel Example: User Story 1

```text
# テストをまとめて書く
T016 OperationStatusRepositoryTest::findLatestBetween
T017 DepartureStatusRepositoryTest::findIrregularBetween
T018 IrregularServiceCollectorTest
T019 NotificationSlotResolverTest
T020 IrregularStatusMailerTest

# 依存の無い部品をまとめて作る
T022 OperationStatusRepository::findLatestBetween
T023 DepartureStatusRepository::findIrregularBetween
T024 View/IrregularPort
T027 Service/NotificationSlotResolver
T028 templates/email/irregular_statuses.txt.twig
```

---

## Implementation Strategy

### MVP（US1 だけ）

1. Phase 1・2 → Phase 3
2. **止めて確かめる**：`make notify-dry-run` の本文を V1 のメールと並べ、Mailpit で 1 通・2 回目は「処理済み」
3. US2（件名のテスト）と US3（失敗の扱い）を足して PR1

### 段階的に出す

1. PR1 をマージ・デプロイ → cron が無いので何も送らない（安全）。本番で `bin/console app:notify-irregular-statuses --dry-run --slot=6` を手で動かして本文を確かめられる
2. VPS の `.env.production` に 3 つを入れる
3. PR2 をマージ・デプロイ → 次の確認時刻から届く
4. 1 週間 V1 と並べて比べ、V1 の通知を止めるのは別作業（spec の Out of Scope）
