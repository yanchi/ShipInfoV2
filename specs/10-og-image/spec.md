# Feature Specification: OG 画像を出す

**Feature Branch**: `10-og-image`
**Created**: 2026-10-06
**Status**: Draft
**Input**: User description: "OG 画像を出す。今は og:image が無く twitter:card が summary なので、LINE・X・Slack などでシェアしたときにタイトルと説明しか出ない。1200×630 の OG 画像（サイト名「鹿児島〜沖縄フェリー運航情報」と V1 配色の青・ファビコンと同じ船のモチーフ）を app/public に置き、全ページの head に og:image（絶対 URL）・og:image:width・og:image:height・og:image:alt を出し、twitter:card を summary_large_image にする。7-v1-branding の FR-008（OG 画像は出さない）を置き換える。画像は全ページ共通の 1 枚でよい。"

## 概要

7-v1-branding では V1 にそろえるため OG 画像を出さなかった（FR-008）。そのため LINE・X・Slack などに URL を貼ると、タイトルと説明文だけの小さなカードになり、ほかの投稿に埋もれる。
サイトの見た目（青いヘッダー・船のファビコン）と同じテイストの大きな画像をカードに出し、シェアされた URL が「あのフェリー運航情報のサイト」とひと目で分かるようにする。

### 現状（2026-10-06 時点）

| 項目 | 今 | この機能の後 |
|------|----|----|
| og:image | なし | 全ページ共通の 1 枚（1200×630） |
| og:image:width / height / alt | なし | あり |
| twitter:card | summary（小さいカード） | summary_large_image（大きい画像のカード） |
| og:title・og:description・og:url・og:type・og:site_name・canonical | あり | 変えない |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - シェアした URL が画像つきのカードで出る（Priority: P1）

利用者が運航情報のページ（トップ・港別・会社別）の URL を LINE・X・Slack などに貼ると、サイト名入りの大きな画像つきのカードが出る。受け取った家族・同行者は、カードを見ただけでフェリーの運航情報のサイトだと分かり、開いてくれる。

**Why this priority**: この機能の目的そのもの。画像の無いカードは目に入りにくく、クリックされにくい。

**Independent Test**: どのページの `<head>` にも OG 画像の情報が出ていて、画像の URL を開くと 1200×630 の画像が返ることを確かめる。本番に出した後、SNS のカード確認ツール（または OG を読み取るツール）に URL を入れて大きい画像のカードになることを確かめる。

**Acceptance Scenarios**:

1. **Given** トップ・港別・会社別のどのページでも、**When** `<head>` を見ると、**Then** og:image・og:image:width（1200）・og:image:height（630）・og:image:alt が出ていて、twitter:card は summary_large_image になっている
2. **Given** og:image の値、**When** 見ると、**Then** スキーム・ホストを含む絶対 URL で、全ページで同じ画像を指している
3. **Given** og:image の URL、**When** 開くと、**Then** 1200×630 の画像が返り、V1 配色の青を基調に、ファビコンと同じ船の絵とサイト名「鹿児島〜沖縄フェリー運航情報」が描かれている
4. **Given** 本番の URL、**When** SNS のカード確認ツールに入れると、**Then** タイトル・説明文と一緒に大きな画像が出る

### Edge Cases

- 会社別ページで存在しない会社を開いたときのエラーページなど、ほかのページと同じ head を使うページにも同じ OG 画像が出ること
- ローカルや v2 のホストで開いたときは、og:image もそのホストを指すこと（og:url・canonical と同じ考え方。本番を指さない）
- 画像の中の文字は、スマートフォンの小さなカード（幅 300px 程度に縮んだ表示）でもサイト名が読める大きさであること
- 画像の端（上下左右）は SNS によって切られることがあるため、サイト名・船の絵は中央寄りに置き、端で切れても意味が通ること
- 画像の差し替え時に SNS 側の古いキャッシュが残っても、ページの表示・機能には影響しないこと

## Requirements *(mandatory)*

### Functional Requirements

**画像**

- **FR-001**: 全ページ共通の OG 画像を 1 枚用意すること。大きさは 1200×630、形式は主要な SNS・チャットがそのまま表示できる一般的な画像形式にすること
- **FR-002**: 画像は V1 配色の青（#0073e6）を基調にし、ファビコンと同じ船の絵とサイト名「鹿児島〜沖縄フェリー運航情報」を入れること。「ShipInfo」という名前は入れないこと（7-v1-branding の FR-003 と同じ）
- **FR-003**: サイト名と船の絵は画像の中央寄りに置き、上下左右の端から少なくとも画像の幅・高さの 1 割は離すこと
- **FR-004**: 画像のファイルの大きさは 300KB 以下にすること（SNS が取得に失敗しにくく、表示が遅れない大きさ）

**head に出す情報**

- **FR-005**: すべてのページに og:image を出し、値はスキーム・ホストを含む絶対 URL にすること。スキーム・ホストはリクエストのものにすること（og:url・canonical と同じ）
- **FR-006**: すべてのページに og:image:width（1200）・og:image:height（630）・og:image:alt を出すこと。alt は画像の内容を表す文（サイト名を含む）にすること
- **FR-007**: twitter:card を summary_large_image にすること
- **FR-008**: 7-v1-branding の FR-008（OG 画像は出さない）はこの機能で置き換える。それ以外の OG・Twitter カード・canonical の値（7-v1-branding の FR-006・FR-007）は変えないこと

**会社名の表記**

- **FR-009**: 会社の呼び名は「Aライン」ではなく「マルエーフェリー」で出すこと。OG 画像の文字と、説明文（description・og:description）の両方に当てはめる。検索でよく使われる表記に合わせ、「A"LINE」のような記号入りの表記は使わない

### Key Entities

- **OG 画像**: 全ページ共通の 1 枚の画像。サイトの公開ディレクトリに置き、固定の URL で取得できる。幅・高さ・代わりの文（alt）を持つ

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: トップ・港別・会社別・エラーページのすべて（100%）で、og:image・og:image:width・og:image:height・og:image:alt が出て、twitter:card が summary_large_image になっている
- **SC-002**: og:image の URL を開くと、1200×630・300KB 以下の画像が返る
- **SC-003**: 本番の URL を SNS のカード確認ツールに入れると、大きな画像つきのカードが出る（少なくとも 1 つのツールで確認）
- **SC-004**: 幅 300px 程度に縮めて表示した画像で、サイト名が読める（開発者が目で確認）
- **SC-005**: OG・Twitter カード・canonical に関する既存のテストが、OG 画像の有無を確かめる部分を除き、変更後もすべて通る

## Assumptions

- 画像は 1 枚を全ページで使う。ページごと・会社ごとに画像を変えたり、運航状況に合わせて画像を作り直したりはしない
- 画像はリポジトリに入れて、アプリと一緒に配る（実行時に画像を作らない）
- 画像の文字の書体・細かいレイアウトは、V1 のヘッダーのテイスト（青地に白い文字）に合わせて開発者が決める
- 同じドメイン（`ship.isl-mentor.com`）で公開する前提は 7-v1-branding と同じ

## Out of Scope

- ページごと・会社ごと・運航状況ごとに異なる OG 画像
- 実行時に画像を作る仕組み
- og:title・og:description などの文言の変更（FR-009 の会社名の表記を除く）
- SNS 側のキャッシュを消す作業（必要なら公開後に各 SNS のツールで行う）
