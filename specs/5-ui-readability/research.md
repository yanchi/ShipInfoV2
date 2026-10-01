# Research: 運航情報画面の見やすさ改善

**Feature**: [spec.md](spec.md) | **Date**: 2026-10-01

現状のコードは次のとおり（調査時点）。

- 画面は `StatusController` の3アクション（`/`・`/company/{id}`・`/ports`）と Twig 4ファイル
- 港別ページは `PortBoardBuilder` が `PortBoard → PortBoardDay → PortBoardDirection → PortBoardRow → PortBoardEntry` の表示用オブジェクト（`app/src/View/`）を組み立てる
- CSS・JS は CDN の Bootstrap 5.3 だけ。アセットのビルド環境（AssetMapper・webpack）は無い
- `departure_statuses.checked_at` は、出港前の行ならスクレイパーが実行のたびに更新する（内容が同じでも更新、出港済みで確定した行だけ更新しない）

---

## R1. 絞り込みの状態をどこに持つか

**Decision**: クエリパラメータ（`/ports?port={portId}&dir={down|up}`）で絞り込み、サーバー側で行を絞る。最後に選んだ条件は **Cookie**（`port_filter`）に保存し、サーバーが読む。

- `/ports` にパラメータがあれば、それで絞り込み、Cookie を書き換える
- `/ports` にパラメータが無く Cookie があれば、Cookie の条件で絞り込む
- 「全港に戻す」は `/ports?port=all`。Cookie を消して全港表示にする
- Cookie の値が不正（存在しない港など）なら無視して Cookie を消す

**Rationale**:
- サーバー側で絞るので JS 無しで動き、絞り込み後の HTML がそのまま短くなる（SC-002）
- Cookie はサーバーが最初のレスポンスで読めるので、トップ（FR-015）でも保存した港の便を出せる。localStorage だと JS で読み直してから描き直すことになり、ちらつく
- Cookie は利用者の端末に保存され、サーバーには何も保存しない（spec の Key Entities どおり）

**Alternatives considered**:
- localStorage と JS での絞り込み：トップで保存した港を出すには JS での描画が必要になり、JS 無しの経路も別に要る
- URL だけ（保存しない）：FR-003（次回も同じ港）を満たせない

## R2. 港の指定に使う値

**Decision**: 港の ID（`ports.id`）を使う。方向は `RouteDirectionEnum` の値（`down` / `up`）。

**Rationale**: `ports` に英字のコードやスラッグが無い。日本語の港名を URL に入れるとエンコードされて読めないし、別名（`aliases`）との揺れも出る。ID なら DB を変えずに済む。

**Alternatives considered**: `ports` にスラッグ列を追加する → DB 変更が要り、spec の「データの保持方法は変えない」に反する。

## R3. 日付への移動（FR-007）

**Decision**: 各日付のセクションにアンカー（`id="d-2026-10-02"`）を付ける。上部の日付ボタンは `position: sticky` で画面上部に残すリンク（`href="#d-2026-10-02"`）にする。JS は使わない。

**Rationale**: ブラウザの標準機能で済み、壊れにくい。sticky のナビに見出しが隠れないように、セクションに `scroll-margin-top` を付ける。

**Alternatives considered**: Bootstrap の scrollspy（今いる日付を強調できる）→ 便利だけど必須ではない。必要になったら後から足せる。

## R4. 異常の要約の作り方（FR-009〜013）

**Decision**: 新しい `PortAlertSummaryBuilder`（Service）が、**全港の** `PortBoard` から異常の行（status が `cancelled` / `delayed` / `suspended`）を取り出す。絞り込み条件で「表示する項目」と「絞り込みの外の件数」に分ける。

- 各項目は日付・方向・出発港・ステータス・行へのアンカーを持つ
- 行のアンカーは `id="r-2026-10-02-down-3"`（日付・方向・港 ID）
- 「異常なし」の文言は、ボードが空でないときだけ出す（FR-011）

**Rationale**: 絞り込みの外の件数（FR-013）を数えるには全港分が要る。`PortBoardBuilder` は全港分を作り、絞り込みは「作ったボードから行を落とす」段階で行う（R5）。そうすれば要約と一覧が同じデータから作られ、食い違わない。

**Alternatives considered**: Twig の中でボードを走査して数える → テストしにくく、トップと港別で同じロジックが二重になる。

## R5. 絞り込みを適用する場所

**Decision**: `PortBoard::filter(PortFilter $filter): PortBoard` を追加して、絞り込んだ新しいボードを返す。`PortBoardBuilder` は変えない。

**Rationale**: ビルダーの既存ルール（他社運航・便なし・情報なしの判定）とテストに触らずに済む（SC-009）。絞り込みは表示用オブジェクトの単純な選別なので、ビルダーの外に置ける。

## R6. 確認時刻を見出しにまとめる（FR-006）

**Decision**: `PortBoardDirection` に `commonCheckedAt(): ?DateTimeInterface` を追加する。方向内で確認時刻を持つエントリーが全部同じ分（`Y-m-d H:i`）なら、その時刻を返す。Twig はそれを方向の見出しに出し、時刻が違うエントリーだけ行に出す。

**Rationale**: 画面の表示は分単位（`n/j H:i`）なので、比較も分単位にする。秒の違いで見出しにまとまらなくなるのを防ぐ。

**Alternatives considered**: 日付単位でまとめる → 下りと上りでスクレイパーの会社が違い、時刻がずれやすい。方向単位のほうがまとまる率が高い。

## R7. 出港済みの判定（FR-008）

**Decision**: `PortBoardEntry::isDeparted(DateTimeInterface $now): bool`。条件は「`departureAt` が `$now` より前」かつ「status が `operating` または運航予定（status なし）」。`delayed` / `cancelled` / `suspended` は false。`$now` は Controller が渡す（テストで固定できるように）。

## R8. ステータス表示の統一（FR-024〜026）

**Decision**: `_status_badge.html.twig` を見直し、全ステータスの記号・文言・見た目を次の表に揃える（契約：[contracts/ui-status.md](contracts/ui-status.md)）。

- 「運航予定」「便なし」「情報なし」は、記号（○ / — / ？）と見た目（枠線のみ / 文字だけ / 灰色の塗り）の両方で区別する
- 凡例は港別ページに `<details>` で置く（JS 不要・開閉できる）

異常の行（FR-014）は、行の左に太い色付きの線を引き、背景を薄い色（Bootstrap の `*-subtle`）にし、ステータスを太字にする。色が見えなくても、線と太字で区別できる。

## R9. 長い詳細文（FR-028）

**Decision**: 詳細文が 60 文字を超えたら `<details>` にする。`<summary>` に先頭 60 文字＋「…」を出し、開くと全文を出す。

**Rationale**: JS も CSS の line-clamp も不要。開閉の状態がブラウザ標準で分かる。60 文字はスマートフォン幅で約3行。

## R10. サイト全体の最終確認時刻（FR-023）

**Decision**: `DepartureStatusRepository::findLatestCheckedAt(): ?DateTimeImmutable`（`MAX(checked_at)`。有効な会社・有効な航路だけ）。全ページで使うので、Twig 拡張 `SiteExtension` の関数 `site_last_checked_at()` と `site_is_stale()` で base レイアウトから呼ぶ。閾値の 2 時間は定数にする。

**Rationale**:
- `checked_at` は出港前の行ならスクレイパーが実行のたびに更新するので、スクレイパーが止まれば止まった時刻のまま残る。2 時間経てば4回分の失敗になる（spec Clarifications）
- 全ページの Controller に同じ引数を渡すより、Twig 拡張にまとめたほうが漏れない

**Alternatives considered**: `scraper_logs.finished_at` の最大値 → スクレイパーが動いても取得に失敗していれば「動いた」になってしまう。表示しているデータそのものの確認時刻のほうが正しい。

## R11. 共通ヘッダーの「各社」リンク（FR-022）

**Decision**: 同じ `SiteExtension` に `site_companies()`（有効な会社の一覧）を置く。ヘッダーの「各社」は Bootstrap のドロップダウンにする（Bootstrap の JS は読み込み済み）。スマートフォン幅ではヘッダーを折りたたむ（navbar の collapse）。

## R12. トップの構成（FR-015〜018）

**Decision**: トップでも `/ports` と同じく全港4日分の `PortBoard` を作る。

- 異常の要約（R4）を作る。トップは絞り込まない
- Cookie に保存した港があれば、ボードを「その港・今日」に絞って表示する
- 無ければ、港別ページへのボタンを出す
- 会社一覧は今の `findTodayByAllCompanies()` を使う。航路がすべて `no_service` の会社は「本日運航なし」の1行にする

## R13. 会社別ページ（FR-019〜021）

**Decision**:
- 便の行：`PortBoard::forCompany(FerryCompany $company)` で、その会社の便（`state` が `status` か `scheduled` で、会社名が一致するエントリー）だけを残し、エントリーが無くなった行を落とす。日付内に行が1つも無ければ「便なし」の1行にする
- 航路の要約行：`OperationStatusRepository::findUpcomingByCompany($company, $days)`（今日〜3日先、`valid_date >= today`）。航路単位の情報が無い日・航路は要約行を出さない
- 今の `findRecentByCompany()` は会社別ページでしか使っていないので削除する

**Rationale**: 便の行は `/ports` と同じビルダーを通すので、「他社運航」「運航予定」の判定が港別ページと一致する。

## R14. 画面の幅（FR-027・SC-008）

**Decision**: 港別の行は2段にする。1段目は「出発港→到着港」「出港時刻」「ステータス」を `d-flex` で並べ、2段目に補足（船名／会社・着時刻・時点）を `small text-muted` で出す。375px で1段目が収まるよう、到着港は方向の見出しにあるので行では「名瀬発」までに短くする案も実装時に確認する。
