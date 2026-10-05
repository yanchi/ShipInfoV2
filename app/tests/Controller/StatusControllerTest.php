<?php

namespace App\Tests\Controller;

use App\Entity\DepartureStatus;
use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Port;
use App\Entity\Route;
use App\Entity\RouteStop;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\KernelBrowser;
use Symfony\Bundle\FrameworkBundle\Test\WebTestCase;
use Symfony\Component\BrowserKit\Cookie as BrowserCookie;
use Symfony\Component\DomCrawler\Crawler;

class StatusControllerTest extends WebTestCase
{
    /** ブラウザが同じサイトのフォームから送るときに付けるヘッダー（stateless の CSRF トークンの確認に使われる） */
    private const SAME_ORIGIN = ['HTTP_SEC_FETCH_SITE' => 'same-origin'];

    private KernelBrowser $client;

    /** @var int[] テスト内で作成した会社ID（tearDown で関連データごと削除する） */
    private array $createdCompanyIds = [];

    protected function setUp(): void
    {
        $this->client = static::createClient();
    }

    protected function tearDown(): void
    {
        if ($this->createdCompanyIds !== []) {
            // リクエスト後に EntityManager がリセットされている可能性があるため、
            // 管理対象エンティティではなく ID 指定の DQL で消す
            $em = $this->entityManager();
            // routes を参照している departure_statuses・route_stops を先に消す
            $em->createQuery('DELETE FROM App\Entity\DepartureStatus d WHERE d.route IN (SELECT r.id FROM App\Entity\Route r WHERE r.ferryCompany IN (:ids)) OR d.operatedByCompany IN (:ids)')
                ->setParameter('ids', $this->createdCompanyIds)
                ->execute();
            $em->createQuery('DELETE FROM App\Entity\RouteStop s WHERE s.route IN (SELECT r.id FROM App\Entity\Route r WHERE r.ferryCompany IN (:ids))')
                ->setParameter('ids', $this->createdCompanyIds)
                ->execute();
            $em->createQuery('DELETE FROM App\Entity\OperationStatus s WHERE s.route IN (SELECT r.id FROM App\Entity\Route r WHERE r.ferryCompany IN (:ids))')
                ->setParameter('ids', $this->createdCompanyIds)
                ->execute();
            $em->createQuery('DELETE FROM App\Entity\Route r WHERE r.ferryCompany IN (:ids)')
                ->setParameter('ids', $this->createdCompanyIds)
                ->execute();
            $em->createQuery('DELETE FROM App\Entity\FerryCompany c WHERE c.id IN (:ids)')
                ->setParameter('ids', $this->createdCompanyIds)
                ->execute();
            $this->createdCompanyIds = [];
        }

        parent::tearDown();
    }

    public function testIndexReturns200(): void
    {
        $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorExists('body');
    }

    public function testIndexContainsTitle(): void
    {
        $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorTextContains('h1', '現在の運航状況');
    }

    public function testIndexRendersCompanyGrid(): void
    {
        $this->createCompanyWithRoute();

        $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorExists('.row.row-cols-1.row-cols-md-2.row-cols-lg-3');
    }

    public function testCompanyCardsAreGridColumns(): void
    {
        $this->createCompanyWithRoute();

        $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorExists('.row > .col > .card.h-100');
    }

    /**
     * レイアウト変更によるデグレード検知（FR-005）。
     * カード内部の会社名リンク・公式サイトリンク・航路一覧・ステータスバッジが残っていること。
     */
    public function testIndexKeepsCardContent(): void
    {
        $this->createCompanyWithRoute();

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $card = $this->findCard($crawler, 'グリッドテスト会社');
        $this->assertCount(1, $card->filter('.card-header a[href^="/company/"]'));
        $this->assertCount(1, $card->filter('.card-header a[target="_blank"][rel="noopener noreferrer"]'));
        $this->assertStringContainsString('グリッドテスト航路', $card->filter('.list-group')->text());
        $this->assertCount(1, $card->filter('.list-group .list-group-item .status-badge--operating'));
    }

    /**
     * 航路0件の会社もカードとして描画され、「航路情報がありません。」が表示されること（spec Edge Cases）。
     */
    public function testIndexShowsNoRouteMessageForCompanyWithoutRoutes(): void
    {
        $company = (new FerryCompany())
            ->setName('グリッドテスト航路なし会社')
            ->setActive(true);
        $this->persistCompany($company);

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $card = $this->findCard($crawler, 'グリッドテスト航路なし会社');
        $this->assertStringContainsString('航路情報がありません。', $card->text());
    }

    public function testCompanyPageReturns200WhenCompanyExists(): void
    {
        $this->client->request('GET', '/company/1');

        // ID 1 が存在すれば 200、存在しなければ 404（どちらも正常）
        $this->assertContains(
            $this->client->getResponse()->getStatusCode(),
            [200, 404],
            'Expected 200 or 404'
        );
    }

    // ------------------------------------------------------------------
    // 共通ヘッダー・最終確認時刻（US6）
    // ------------------------------------------------------------------

    /** 3画面すべてに同じヘッダーがあり、今いるページに aria-current="page" */
    public function testSharedHeaderOnAllPages(): void
    {
        $this->createPortBoardData();
        $companyId = $this->companyId('港別テスト運航会社');

        foreach (['/' => 'a[href="/"]', '/ports' => 'a[href="/ports"]', "/company/{$companyId}" => "a[href=\"/company/{$companyId}\"]"] as $url => $current) {
            $crawler = $this->client->request('GET', $url);
            $this->assertResponseIsSuccessful($url);

            $nav = $crawler->filter('header.site-header nav');
            $this->assertCount(1, $nav, $url);
            $this->assertCount(1, $nav->filter('a[href="/"]'), $url);
            $this->assertCount(1, $nav->filter('a[href="/ports"]'), $url);
            $this->assertCount(1, $nav->filter("a[href=\"/company/{$companyId}\"]"), $url);
            $this->assertCount(1, $nav->filter('[aria-current="page"]'), $url);
            $this->assertCount(1, $nav->filter($current . '[aria-current="page"]'), $url);
            $this->assertStringNotContainsString('トップへ戻る', $crawler->filter('body')->text(), $url);
        }
    }

    // ------------------------------------------------------------------
    // V1 の見た目・<head>（specs/7-v1-branding）
    // ------------------------------------------------------------------

    /** @return array<string, string> URL => 説明 */
    private function threePages(): array
    {
        $this->createPortBoardData();
        $companyId = $this->companyId('港別テスト運航会社');

        return ['/' => 'top', '/ports' => 'ports', "/company/{$companyId}" => 'company'];
    }

    public function testSiteChromeOnAllPages(): void
    {
        foreach (array_keys($this->threePages()) as $url) {
            $crawler = $this->client->request('GET', $url);
            $this->assertResponseIsSuccessful($url);

            $name = $crawler->filter('.site-header .site-name');
            $this->assertCount(1, $name, $url);
            $this->assertSame('/', $name->attr('href'), $url);
            $this->assertStringContainsString('鹿児島〜沖縄・奄美大島', $name->text(), $url);
            $this->assertStringContainsString('フェリー運航情報', $name->text(), $url);

            $nav = $crawler->filter('.site-header nav')->text();
            foreach (['トップ', '港別', '各社'] as $label) {
                $this->assertStringContainsString($label, $nav, $url);
            }
            $this->assertSame(
                '© 2025 鹿児島〜沖縄・奄美大島 フェリー運航情報サービス',
                trim($crawler->filter('footer.site-footer')->text()),
                $url,
            );
            $this->assertSame('/favicon.svg', $crawler->filter('link[rel="icon"]')->attr('href'), $url);
            $this->assertSame('light', $crawler->filter('html')->attr('data-bs-theme'), $url);
            $this->assertCount(1, $crawler->filter('footer'), $url);
            $this->assertCount(1, $crawler->filter('p.page-note'), $url);
        }
    }

    public function testCurrentPageIsMarkedInNav(): void
    {
        $crawler = $this->client->request('GET', '/ports');
        $this->assertSame('港別', trim($crawler->filter('.site-header nav [aria-current="page"]')->text()));

        $crawler = $this->client->request('GET', '/');
        $this->assertSame('トップ', trim($crawler->filter('.site-header nav [aria-current="page"]')->text()));
    }

    /** 欠航・条件付・遅延の便にだけ V1 の注意書き（FR-016） */
    public function testStatusWarningShownForCancelledAndDelayed(): void
    {
        $this->createPortBoardData(OperationStatusEnum::Cancelled);

        $crawler = $this->client->request('GET', '/ports');
        $this->assertCount(1, $this->findPortRow($crawler, 1, '名瀬')->filter('.port-entry .status-warning'));
        $this->assertStringContainsString('出港時間・寄港地が変更になってる可能性があるので公式サイトをご確認ください', $this->findPortRow($crawler, 1, '名瀬')->filter('.status-warning')->text());
        $this->assertCount(0, $this->findPortRow($crawler, 0, '名瀬')->filter('.status-warning'));

        $this->updateTestDeparture(1, 'status', OperationStatusEnum::Delayed);
        $crawler = $this->client->request('GET', '/ports');
        $this->assertCount(1, $this->findPortRow($crawler, 1, '名瀬')->filter('.status-warning'));

        $this->updateTestDeparture(1, 'status', OperationStatusEnum::Suspended);
        $crawler = $this->client->request('GET', '/ports');
        $this->assertCount(0, $this->findPortRow($crawler, 1, '名瀬')->filter('.status-warning'));
    }

    public function testStatusWarningOnIndexCardAndCompanySummary(): void
    {
        $companyId = $this->createCompanyWithRoute('注意書きテスト会社', OperationStatusEnum::Cancelled);
        $crawler   = $this->client->request('GET', '/');
        $this->assertCount(1, $this->findCard($crawler, '注意書きテスト会社')->filter('.list-group-item .status-warning'));

        $crawler = $this->client->request('GET', "/company/{$companyId}");
        $this->assertCount(1, $crawler->filter('.route-summaries li .status-warning'));

        $operatingId = $this->createCompanyWithRoute('注意書きなし会社', OperationStatusEnum::Operating);
        $crawler     = $this->client->request('GET', '/');
        $this->assertCount(0, $this->findCard($crawler, '注意書きなし会社')->filter('.status-warning'));
        $crawler = $this->client->request('GET', "/company/{$operatingId}");
        $this->assertCount(0, $crawler->filter('.route-summaries .status-warning'));
    }

    public function testPageHeadingsHaveClass(): void
    {
        foreach ($this->threePages() as $url => $kind) {
            $crawler = $this->client->request('GET', $url);
            if ($kind === 'company') {
                $this->assertCount(1, $crawler->filter('div.page-heading > h1'), $url);
            } else {
                $this->assertCount(1, $crawler->filter('h1.page-heading'), $url);
            }
            if ($kind !== 'top') {
                $this->assertGreaterThan(0, $crawler->filter('h2.page-heading')->count(), $url);
            }
        }
    }

    public function testNoDataMessagesUseV1Style(): void
    {
        $crawler = $this->client->request('GET', '/ports');
        $this->assertResponseIsSuccessful();
        // 既存データの有無に依存するので、あるときは .alert-secondary で出さないことだけを確かめる
        $this->assertCount(0, $crawler->filter('.alert-secondary'));
        foreach (['/' => '現在情報がありません。', '/ports' => '港別の情報がありません。'] as $url => $message) {
            $crawler = $this->client->request('GET', $url);
            $noData  = $crawler->filter('.no-data');
            if ($noData->count() > 0) {
                $this->assertStringContainsString($message, $noData->text(), $url);
            }
        }
    }

    // ------------------------------------------------------------------
    // <head>（US2）
    // ------------------------------------------------------------------

    public function testHeadMetaOnAllPages(): void
    {
        foreach (array_keys($this->threePages()) as $url) {
            $crawler = $this->client->request('GET', $url);
            $this->assertResponseIsSuccessful($url);

            $title       = $crawler->filter('title')->text();
            $description = $crawler->filter('meta[name="description"]')->attr('content');
            $canonical   = $crawler->filter('link[rel="canonical"]')->attr('href');
            $this->assertNotSame('', $description, $url);
            $this->assertSame($title, $crawler->filter('meta[property="og:title"]')->attr('content'), $url);
            $this->assertSame($description, $crawler->filter('meta[property="og:description"]')->attr('content'), $url);
            $this->assertSame($canonical, $crawler->filter('meta[property="og:url"]')->attr('content'), $url);
            $this->assertSame('website', $crawler->filter('meta[property="og:type"]')->attr('content'), $url);
            $this->assertSame('鹿児島〜沖縄フェリー運航情報サービス', $crawler->filter('meta[property="og:site_name"]')->attr('content'), $url);
            $this->assertSame('summary', $crawler->filter('meta[name="twitter:card"]')->attr('content'), $url);
            $this->assertCount(0, $crawler->filter('meta[property="og:image"]'), $url);
        }
    }

    public function testTopTitleAndDescription(): void
    {
        $crawler = $this->client->request('GET', '/');

        $this->assertSame('鹿児島〜沖縄・奄美大島フェリー運航情報', $crawler->filter('title')->text());
        $this->assertSame(
            'Aライン・マリックスラインの鹿児島〜那覇・奄美大島間フェリーの最新運航状況。欠航・遅延情報を毎時更新。旅行前に出発港・到着港の運航状況をご確認ください。',
            $crawler->filter('meta[name="description"]')->attr('content'),
        );
    }

    public function testPageTitleFormat(): void
    {
        $crawler = $this->client->request('GET', '/ports');
        $this->assertSame('港別運航情報 | 鹿児島〜沖縄フェリー運航状況', $crawler->filter('title')->text());

        $this->createPortBoardData();
        $id      = $this->companyId('港別テスト運航会社');
        $crawler = $this->client->request('GET', "/company/{$id}");
        $this->assertSame('港別テスト運航会社 運航状況 | 鹿児島〜沖縄フェリー運航状況', $crawler->filter('title')->text());
        $this->assertStringContainsString('港別テスト運航会社', $crawler->filter('meta[name="description"]')->attr('content'));
    }

    /** 社名に & < " ' を含んでも og タグが二重にエスケープされない */
    public function testOgTagsAreNotDoubleEscaped(): void
    {
        $id = $this->createCompanyWithRoute('A&B<汽船>"\'');

        $crawler = $this->client->request('GET', "/company/{$id}");

        $this->assertSame("A&B<汽船>\"' 運航状況 | 鹿児島〜沖縄フェリー運航状況", $crawler->filter('title')->text());
        $this->assertSame($crawler->filter('title')->text(), $crawler->filter('meta[property="og:title"]')->attr('content'));
        $this->assertSame($crawler->filter('meta[name="description"]')->attr('content'), $crawler->filter('meta[property="og:description"]')->attr('content'));
        $this->assertStringContainsString('A&B<汽船>"\'', $crawler->filter('meta[property="og:description"]')->attr('content'));
    }

    /** 本番以外（テスト環境）では GA のタグを出さない（FR-022） */
    public function testNoAnalyticsTagOutsideProd(): void
    {
        foreach (array_keys($this->threePages()) as $url) {
            $this->client->request('GET', $url);
            $html = (string) $this->client->getResponse()->getContent();
            $this->assertStringNotContainsString('googletagmanager.com', $html, $url);
            $this->assertStringNotContainsString('gtag(', $html, $url);
        }
    }

    public function testCanonicalExcludesQueryString(): void
    {
        $crawler = $this->client->request('GET', '/ports?port=all&dir=down');

        $this->assertSame('http://localhost/ports', $crawler->filter('link[rel="canonical"]')->attr('href'));
        $this->assertSame('http://localhost/ports', $crawler->filter('meta[property="og:url"]')->attr('content'));
    }

    public function testNoShipInfoAnywhere(): void
    {
        foreach (array_keys($this->threePages()) as $url) {
            $this->client->request('GET', $url);
            $this->assertStringNotContainsString('ShipInfo', (string) $this->client->getResponse()->getContent(), $url);
        }
    }

    public function testFreshnessWithoutWarningWhenRecent(): void
    {
        $this->createPortBoardData();
        $this->setCheckedAt(null, '-10 minutes');

        foreach (['/', '/ports'] as $url) {
            $crawler = $this->client->request('GET', $url);

            $this->assertCount(0, $crawler->filter('.site-freshness.alert'), $url);
            $this->assertStringContainsString('最終確認 ' . (new \DateTimeImmutable('-10 minutes'))->format('n/j'), $crawler->filter('.site-freshness')->text(), $url);
        }
    }

    /** 1社だけ古い → 他の会社が新しくても警告とその会社名 */
    public function testFreshnessWarnsWhenOneCompanyIsStale(): void
    {
        $this->createPortBoardData();
        $this->setCheckedAt(null, '-10 minutes');
        $this->setCheckedAt('港別テスト非運航会社', '-3 hours');

        foreach (['/', '/ports', '/company/' . $this->companyId('港別テスト運航会社')] as $url) {
            $crawler = $this->client->request('GET', $url);

            $warning = $crawler->filter('.site-freshness.alert-warning');
            $this->assertCount(1, $warning, $url);
            $this->assertStringContainsString('情報が古い可能性があります', $warning->text(), $url);
            $this->assertStringContainsString('港別テスト非運航会社', $warning->text(), $url);
            $this->assertStringNotContainsString('港別テスト運航会社 ', $warning->text(), $url);
        }
    }

    // ------------------------------------------------------------------
    // /company/{id}（会社別、US5）
    // ------------------------------------------------------------------

    /** 今日〜3日先。便あり・便なし・情報なしを区別する */
    public function testCompanyPageShowsUpcomingDaysWithStates(): void
    {
        $this->createPortBoardData();
        $today = new \DateTimeImmutable('today');

        $crawler = $this->client->request('GET', '/company/' . $this->companyId('港別テスト運航会社'));

        $this->assertResponseIsSuccessful();
        $sections = $crawler->filter('section.company-day');
        $this->assertCount(4, $sections);
        $headings = implode(' ', $crawler->filter('section.company-day h2')->each(static fn (Crawler $n) => trim($n->text())));
        for ($i = 0; $i < 4; ++$i) {
            $this->assertSame('d-' . $today->modify("+{$i} days")->format('Y-m-d'), $sections->eq($i)->attr('id'));
        }
        $this->assertStringNotContainsString($today->modify('-1 day')->format('n月j日（'), $headings);

        // 今日：便あり（自社の便だけ）
        $rows = $sections->eq(0)->filter('li.port-row');
        $this->assertCount(1, $rows);
        $this->assertStringStartsWith('名瀬発', trim($rows->filter('.fw-bold')->text()));
        $this->assertStringContainsString('港別テスト丸／港別テスト運航会社', $rows->text());
        // 明日：行が無い → 情報なし
        $this->assertCount(0, $sections->eq(1)->filter('li.port-row'));
        $this->assertStringContainsString('？ 情報なし', $sections->eq(1)->filter('.company-day-state')->text());
        // 3日先：運航予定 → 便あり
        $this->assertCount(1, $sections->eq(3)->filter('li.port-row'));
    }

    public function testCompanyPageShowsNoServiceDay(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/company/' . $this->companyId('港別テスト非運航会社'));

        $today = $crawler->filter('section.company-day')->eq(0);
        $this->assertCount(0, $today->filter('li.port-row'));
        $this->assertStringContainsString('— 便なし', $today->filter('.company-day-state')->text());
    }

    public function testCompanyPageShowsRouteSummaryOnlyOnDaysWithInfo(): void
    {
        $this->createPortBoardData();
        $this->persistOperationStatus('港別テスト運航会社 下り', 1, OperationStatusEnum::Delayed, '天候不良のため条件付き');

        $crawler  = $this->client->request('GET', '/company/' . $this->companyId('港別テスト運航会社'));
        $sections = $crawler->filter('section.company-day');

        $this->assertCount(0, $sections->eq(0)->filter('.route-summaries'));
        $summary = $sections->eq(1)->filter('.route-summaries');
        $this->assertCount(1, $summary);
        $this->assertStringContainsString('港別テスト運航会社 下り', $summary->text());
        $this->assertStringContainsString('▲ 条件付・遅延', $summary->text());
        $this->assertStringContainsString('└ 天候不良のため条件付き', $summary->text());
    }

    /** 航路単位では便なしでも、その方向の便が途中の港を出る日は要約行を出さない（tasks T054a） */
    public function testCompanyPageHidesNoServiceSummaryWhenDepartingMidway(): void
    {
        $this->createPortBoardData();
        $this->persistOperationStatus('港別テスト運航会社 下り', 0, OperationStatusEnum::NoService);

        $crawler = $this->client->request('GET', '/company/' . $this->companyId('港別テスト運航会社'));
        $today   = $crawler->filter('section.company-day')->eq(0);

        $this->assertCount(0, $today->filter('.route-summaries'));
        $this->assertCount(1, $today->filter('li.port-row'));
    }

    /** 無効な会社は 404（港別ボードにも共通ヘッダーにも出ないため） */
    public function testCompanyPageReturns404ForInactiveCompany(): void
    {
        $company = (new FerryCompany())->setName('無効テスト会社')->setActive(false);
        $id      = $this->persistCompany($company);

        $this->client->request('GET', "/company/{$id}");

        $this->assertResponseStatusCodeSame(404);
    }

    public function testCompanyPageReturns404ForNonExistentId(): void
    {
        $this->client->request('GET', '/company/999999');

        $this->assertResponseStatusCodeSame(404);
    }

    // ------------------------------------------------------------------
    // /ports（港別運航情報）
    // ------------------------------------------------------------------

    public function testPortsReturns200(): void
    {
        $this->client->request('GET', '/ports');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorTextContains('h1', '港別運航情報');
    }

    public function testPortsShowsTodayToThreeDaysAheadOnly(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $this->assertResponseIsSuccessful();
        $headings = $crawler->filter('h2')->each(static fn (Crawler $n) => trim($n->text()));
        $today    = new \DateTimeImmutable('today');
        for ($i = 0; $i < 4; ++$i) {
            $this->assertStringContainsString($today->modify("+{$i} days")->format('n月j日'), implode(' ', $headings));
        }
        $this->assertStringNotContainsString($today->modify('-1 day')->format('n月j日（'), implode(' ', $headings));
        $this->assertStringNotContainsString($today->modify('+4 days')->format('n月j日（'), implode(' ', $headings));
    }

    public function testPortsShowsOperatingCompanyOnly(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $row = $this->findPortRow($crawler, 0, '名瀬');
        $this->assertStringContainsString('港別テスト丸／港別テスト運航会社', $row->text());
        $this->assertStringContainsString('05:50発', $row->text());
        $this->assertCount(1, $row->filter('.status-badge--operating'));
        $this->assertStringNotContainsString('便なし', $row->text());
        $this->assertStringNotContainsString('港別テスト非運航会社', $row->text());
    }

    public function testPortsShowsScheduledBadge(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $row = $this->findPortRow($crawler, 3, '名瀬');
        $this->assertStringContainsString('運航予定', $row->filter('.status-badge--scheduled')->text());
        $this->assertCount(0, $row->filter('.status-badge--operating'));
    }

    /** 方向内の確認時刻が全部同じ分なら、方向の見出しに1回だけ出して、行には出さない（FR-006） */
    public function testPortsShowsCheckedAt(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $expected = (new \DateTimeImmutable('today'))->setTime(6, 0)->format('n/j H:i') . '時点';
        $heading  = $crawler->filter('section')->eq(0)->filter('h3')->first();
        $this->assertSame($expected, trim($heading->filter('.checked-at')->text()));
        $this->assertStringNotContainsString('時点', $this->findPortRow($crawler, 0, '名瀬')->text());
    }

    /** 確認時刻が違うエントリーがあれば見出しにまとめず、行ごとに出す */
    public function testPortsShowsCheckedAtOnRowsWhenDifferent(): void
    {
        $this->createPortBoardData();
        $this->updateTestDeparture(0, 'checkedAt', (new \DateTime('today'))->setTime(5, 0));

        $crawler = $this->client->request('GET', '/ports');

        $this->assertCount(0, $crawler->filter('section')->eq(0)->filter('h3')->first()->filter('.checked-at'));
        $expected = (new \DateTimeImmutable('today'))->setTime(5, 0)->format('n/j H:i') . '時点';
        $this->assertStringContainsString($expected, $this->findPortRow($crawler, 0, '名瀬')->text());
    }

    public function testPortsHasDateNavigation(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $links = $crawler->filter('.date-nav a[href^="#d-"]');
        $this->assertCount(4, $links);
        $today = new \DateTimeImmutable('today');
        for ($i = 0; $i < 4; ++$i) {
            $id = 'd-' . $today->modify("+{$i} days")->format('Y-m-d');
            $this->assertSame('#' . $id, $links->eq($i)->attr('href'));
            $this->assertCount(1, $crawler->filter("section#{$id}"));
        }
    }

    public function testPortsFoldsLongDetail(): void
    {
        $this->createPortBoardData();
        $long  = str_repeat('天候不良のため条件付きで運航します。', 5);
        $short = '天候に注意';
        $this->updateTestDeparture(0, 'statusDetail', $long);
        $this->updateTestDeparture(3, 'statusDetail', $short);

        $crawler = $this->client->request('GET', '/ports');

        $details = $this->findPortRow($crawler, 0, '名瀬')->filter('details');
        $this->assertCount(1, $details);
        $this->assertSame(mb_substr($long, 0, 60) . '…', trim($details->filter('summary')->text()));
        // 開いたときに先頭60文字が2回出ない
        $this->assertSame(1, mb_substr_count($details->text(), mb_substr($long, 0, 60)));
        $this->assertStringContainsString(mb_substr($long, 60), $details->text());
        $later = $this->findPortRow($crawler, 3, '名瀬');
        $this->assertCount(0, $later->filter('details'));
        $this->assertStringContainsString('└ ' . $short, $later->text());
    }

    public function testPortsHasStatusLegend(): void
    {
        $crawler = $this->client->request('GET', '/ports');

        $legend = $crawler->filter('details.status-legend');
        $this->assertCount(1, $legend);
        foreach (['✓ 通常運航', '○ 運航予定', '▲ 条件付・遅延', '✗ 欠航', '■ 運休', '— 便なし', '？ 情報なし', '？ 不明'] as $label) {
            $this->assertStringContainsString($label, $legend->text());
        }
    }

    /**
     * 前日に始発港を出た便でも、その港を出る日の日付セクションに出る（US5 シナリオ1）。
     * 到着が翌日なら「翌H:i着」。
     */
    public function testPortsShowsIntermediatePortUnderItsDepartureDate(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        // 今日の名瀬発（前日鹿児島発の便）は今日のセクション
        $row = $this->findPortRow($crawler, 0, '名瀬');
        $this->assertStringContainsString('05:50発', $row->text());
        $this->assertStringContainsString('翌08:00着', $row->text());
        // 翌日のセクションの名瀬発には出ない
        $this->assertStringNotContainsString('港別テスト丸', $this->findPortRow($crawler, 1, '名瀬')->text());
    }

    // ------------------------------------------------------------------
    // /ports の絞り込み（US1）
    // ------------------------------------------------------------------

    public function testPortsFilterByPortAndDirection(): void
    {
        $this->createPortBoardData();
        $naze = $this->portId('名瀬');

        $crawler = $this->client->request('GET', "/ports?port={$naze}&dir=down");

        $this->assertResponseIsSuccessful();
        $rows = $crawler->filter('li.port-row');
        $this->assertCount(4, $rows);
        foreach ($rows as $row) {
            $this->assertStringStartsWith('名瀬発', trim((new Crawler($row))->filter('.fw-bold')->text()));
        }
        $this->assertCount(4, $crawler->filter('section[id^="d-"]'));
        $this->assertStringContainsString('名瀬発・下りのみ表示中', $crawler->filter('.filter-status')->text());
        $this->assertCount(1, $crawler->filter('a[href="/ports?port=all"]'));
        $this->assertCount(0, $crawler->selectButton('保存を解除'));
        $this->assertSame([], $this->client->getResponse()->headers->getCookies());
    }

    /** フォームの「この港を保存」→ POST /ports/filter → Cookie を書いて GET にリダイレクト（PRG） */
    public function testPortsSaveWritesCookieAndRedirects(): void
    {
        $this->createPortBoardData();
        $naze = $this->portId('名瀬');

        $crawler = $this->client->request('GET', '/ports');
        $form    = $crawler->selectButton('この港を保存')->form(['port' => (string) $naze, 'dir' => 'down']);
        $this->client->submit($form, [], self::SAME_ORIGIN);

        $this->assertResponseStatusCodeSame(303);
        $response = $this->client->getResponse();
        $this->assertSame("/ports?port={$naze}&dir=down", $response->headers->get('Location'));
        $cookies = $response->headers->getCookies();
        $this->assertCount(1, $cookies);
        $this->assertSame('port_filter', $cookies[0]->getName());
        $this->assertSame("port={$naze}&dir=down", $cookies[0]->getValue());

        // 次に /ports を開くと保存した条件
        $crawler = $this->client->request('GET', '/ports');
        $this->assertCount(4, $crawler->filter('li.port-row'));
        $this->assertCount(1, $crawler->selectButton('保存を解除'));
    }

    /** 「表示」は保存せず、条件の URL にリダイレクトするだけ */
    public function testPortsShowRedirectsWithoutSaving(): void
    {
        $this->createPortBoardData();
        $naze = $this->portId('名瀬');

        $crawler = $this->client->request('GET', '/ports');
        $this->client->submit($crawler->selectButton('表示')->form(['port' => (string) $naze, 'dir' => 'down']), [], self::SAME_ORIGIN);

        $this->assertResponseStatusCodeSame(303);
        $this->assertSame("/ports?port={$naze}&dir=down", $this->client->getResponse()->headers->get('Location'));
        $this->assertSame([], $this->client->getResponse()->headers->getCookies());
    }

    /** 他のサイトからの POST やトークンの無い POST では保存しない（CSRF） */
    public function testPortsSaveFromOtherSiteIsIgnored(): void
    {
        $this->createPortBoardData();
        $naze = $this->portId('名瀬');

        $crawler = $this->client->request('GET', '/ports');
        $form    = $crawler->selectButton('この港を保存')->form(['port' => (string) $naze, 'dir' => 'down']);
        $this->client->submit($form, [], ['HTTP_SEC_FETCH_SITE' => 'cross-site']);
        $this->assertResponseStatusCodeSame(303);
        $this->assertSame([], $this->client->getResponse()->headers->getCookies());

        $this->client->request('POST', '/ports/filter', ['action' => 'save', 'port' => (string) $naze, 'dir' => 'down'], [], self::SAME_ORIGIN);
        $this->assertResponseStatusCodeSame(303);
        $this->assertSame([], $this->client->getResponse()->headers->getCookies());
    }

    /** GET の save=1・clear=1 では Cookie を変えない（リンクで書き換えられないように） */
    public function testPortsGetSaveAndClearAreIgnored(): void
    {
        foreach (['/ports?port=' . $this->portId('名瀬') . '&save=1', '/ports?clear=1'] as $url) {
            $this->client->request('GET', $url);
            $this->assertResponseIsSuccessful($url);
            $this->assertSame([], $this->client->getResponse()->headers->getCookies(), $url);
        }
    }

    public function testPortsAllKeepsSavedCookie(): void
    {
        $this->createPortBoardData();
        $this->client->getCookieJar()->set(new BrowserCookie('port_filter', 'port=' . $this->portId('名瀬')));

        $crawler = $this->client->request('GET', '/ports?port=all');

        $this->assertResponseIsSuccessful();
        $this->assertGreaterThan(4, $crawler->filter('li.port-row')->count());
        $this->assertSame([], $this->client->getResponse()->headers->getCookies());
        $this->assertCount(1, $crawler->selectButton('保存を解除'));
    }

    public function testPortsClearRemovesCookie(): void
    {
        $this->createPortBoardData();
        $this->client->getCookieJar()->set(new BrowserCookie('port_filter', 'port=' . $this->portId('名瀬')));

        $crawler = $this->client->request('GET', '/ports');
        $this->client->submit($crawler->selectButton('保存を解除')->form(), [], self::SAME_ORIGIN);

        $this->assertResponseStatusCodeSame(303);
        $this->assertSame('/ports', $this->client->getResponse()->headers->get('Location'));
        $cookies = $this->client->getResponse()->headers->getCookies();
        $this->assertCount(1, $cookies);
        $this->assertSame('port_filter', $cookies[0]->getName());
        $this->assertTrue($cookies[0]->isCleared());
    }

    public function testPortsInvalidParamsReturn200(): void
    {
        foreach (['/ports?port=999', '/ports?dir=xxx'] as $url) {
            $this->client->request('GET', $url);
            $this->assertResponseIsSuccessful($url);
        }
    }

    public function testPortsIsPrivateAndVariesByCookie(): void
    {
        $this->client->request('GET', '/ports');

        $headers = $this->client->getResponse()->headers;
        $this->assertTrue($headers->hasCacheControlDirective('private'));
        $this->assertContains('Cookie', $this->client->getResponse()->getVary());
    }

    // ------------------------------------------------------------------
    // /ports の異常の要約（US2）
    // ------------------------------------------------------------------

    public function testPortsAlertSummaryLinksToRow(): void
    {
        $this->createPortBoardData(OperationStatusEnum::Cancelled);
        $anchor = sprintf('r-%s-down-%d', (new \DateTimeImmutable('tomorrow'))->format('Y-m-d'), $this->portId('名瀬'));

        $crawler = $this->client->request('GET', '/ports');

        $this->assertResponseIsSuccessful();
        $link = $crawler->filter(".alert-summary a[href=\"#{$anchor}\"]");
        $this->assertCount(1, $link);
        $this->assertStringContainsString('名瀬発→', $link->text());
        $this->assertStringContainsString('✗ 欠航', $link->text());
        $this->assertCount(1, $crawler->filter("li#{$anchor} .port-entry.port-entry--alert.port-entry--cancelled"));
    }

    public function testPortsAlertSummaryShowsHiddenCountWhenFiltered(): void
    {
        $this->createPortBoardData(OperationStatusEnum::Cancelled);

        $crawler = $this->client->request('GET', '/ports?port=' . $this->portId('鹿児島') . '&dir=down');

        $this->assertResponseIsSuccessful();
        $this->assertMatchesRegularExpression('/絞り込みの外にも欠航・条件付などがあります（[1-9]\d*件）/u', $crawler->filter('.alert-summary')->text());
    }

    public function testPortsAlertSummaryWithoutAlerts(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $this->assertStringContainsString('表示期間内に欠航・条件付の便はありません', $crawler->filter('.alert-summary')->text());
    }

    // ------------------------------------------------------------------
    // /（トップ、US4）
    // ------------------------------------------------------------------

    /** 保存した港が無ければ、港別ページへのボタン相当の導線（FR-017） */
    public function testIndexLinksToPorts(): void
    {
        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $button = $crawler->filter('a.ports-cta.btn.btn-lg[href="/ports"]');
        $this->assertCount(1, $button);
        $this->assertStringContainsString('自分の港の便を見る', $button->text());
    }

    public function testIndexWithoutCookieShowsSummaryAndButton(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertCount(1, $crawler->filter('.alert-summary'));
        $this->assertCount(1, $crawler->filter('a.ports-cta'));
        $this->assertCount(0, $crawler->filter('.saved-today'));
        // 方向ごとの便の概要は出さない（FR-016）
        $this->assertCount(0, $crawler->filter('li.port-row'));
    }

    public function testIndexWithSavedPortShowsTodaysDepartures(): void
    {
        $this->createPortBoardData();
        $this->client->getCookieJar()->set(new BrowserCookie('port_filter', 'port=' . $this->portId('名瀬') . '&dir=down'));

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $saved = $crawler->filter('.saved-today');
        $this->assertCount(1, $saved);
        $this->assertStringContainsString('名瀬発・下りの今日の便', $saved->filter('h2')->text());
        $rows = $saved->filter('li.port-row');
        $this->assertCount(1, $rows);
        $this->assertStringContainsString('05:50発', $rows->text());
        $this->assertCount(1, $saved->filter('a[href="/ports"]'));
        $this->assertCount(0, $crawler->filter('a.ports-cta'));
    }

    /** トップはクエリを見ない（絞り込みも保存もリダイレクトもしない） */
    public function testIndexIgnoresQuery(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/?port=' . $this->portId('名瀬') . '&dir=down&save=1');

        $this->assertResponseIsSuccessful();
        $this->assertSame([], $this->client->getResponse()->headers->getCookies());
        $this->assertCount(0, $crawler->filter('.saved-today'));
        $this->assertCount(1, $crawler->filter('a.ports-cta'));
    }

    /** 保存した条件に合う行が無い（その方向では出発港にならない港）ときは、空の箱ではなく文言を出す */
    public function testIndexSavedFilterWithoutRowsShowsMessage(): void
    {
        $this->createPortBoardData();
        // テストデータは下りの航路だけなので、「鹿児島発・上り」は港も方向も正しいが、合う行が無い
        $this->client->getCookieJar()->set(new BrowserCookie('port_filter', 'port=' . $this->portId('鹿児島') . '&dir=up'));

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $saved = $crawler->filter('.saved-today');
        $this->assertCount(1, $saved);
        $this->assertCount(0, $saved->filter('.card'));
        $this->assertStringContainsString('条件に合う便はありません。', $saved->text());
    }

    public function testIndexClearsInvalidCookie(): void
    {
        $this->client->getCookieJar()->set(new BrowserCookie('port_filter', 'port=999999'));

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertCount(1, $crawler->filter('a.ports-cta'));
        $cookies = $this->client->getResponse()->headers->getCookies();
        $this->assertCount(1, $cookies);
        $this->assertSame('port_filter', $cookies[0]->getName());
        $this->assertTrue($cookies[0]->isCleared());
    }

    /** 要約は全港・4日分。リンクは /ports?port=all#r-…（保存した港に関係なく行に着地する） */
    public function testIndexAlertSummaryLinksToPortsAll(): void
    {
        $this->createPortBoardData(OperationStatusEnum::Cancelled);
        $this->client->getCookieJar()->set(new BrowserCookie('port_filter', 'port=' . $this->portId('鹿児島')));
        $anchor = sprintf('r-%s-down-%d', (new \DateTimeImmutable('tomorrow'))->format('Y-m-d'), $this->portId('名瀬'));

        $crawler = $this->client->request('GET', '/');

        $this->assertCount(1, $crawler->filter(".alert-summary a[href=\"/ports?port=all#{$anchor}\"]"));
        $this->assertStringNotContainsString('絞り込みの外にも', $crawler->filter('.alert-summary')->text());
    }

    /** 航路がすべて no_service の会社は「本日運航なし」の1行にまとめる（FR-018） */
    public function testIndexCollapsesCompanyWithoutServiceToday(): void
    {
        $this->createCompanyWithRoute();
        $this->createCompanyWithRoute('運航なしテスト会社', OperationStatusEnum::NoService);

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertStringContainsString('運航なしテスト会社：本日運航なし', $crawler->filter('.idle-companies')->text());
        $this->assertCount(0, $crawler->filter('.card-header')->reduce(
            static fn (Crawler $n) => str_contains($n->text(), '運航なしテスト会社'),
        ));
        $this->findCard($crawler, 'グリッドテスト会社');
    }

    /**
     * 航路単位では no_service でも、前日に始発港を出た便が今日途中の港を出るなら「本日運航なし」にしない。
     */
    public function testIndexKeepsCompanyWithDeparturesTodayAsCard(): void
    {
        $this->createPortBoardData();
        $this->persistOperationStatus('港別テスト運航会社 下り', 0, OperationStatusEnum::NoService);

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $card = $this->findCard($crawler, '港別テスト運航会社');
        $this->assertCount(0, $crawler->filter('.idle-companies'));
        // 下りは航路単位の「便なし」ではなく、始発港を除いた港の便の状態を出す（tasks T054a）
        $this->assertStringContainsString('✓ 通常運航', $card->text());
        $this->assertStringNotContainsString('便なし', $card->text());
    }

    /** 上りも同じ：前日に那覇を出た便が今日名瀬を出るなら、名瀬発の便の状態を出す */
    public function testIndexShowsMidwayStatusForUpRoute(): void
    {
        $this->createPortBoardData(direction: RouteDirectionEnum::Up);
        $this->persistOperationStatus('港別テスト運航会社 上り', 0, OperationStatusEnum::NoService);

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $card = $this->findCard($crawler, '港別テスト運航会社');
        $this->assertStringContainsString('✓ 通常運航', $card->text());
        $this->assertStringNotContainsString('便なし', $card->text());
    }

    /** 途中の港を出る便が全部欠航なら、そのまま「欠航」と出す */
    public function testIndexShowsMidwayStatusAsIsWhenUniform(): void
    {
        $this->createPortBoardData();
        $this->persistOperationStatus('港別テスト運航会社 下り', 0, OperationStatusEnum::NoService);
        $this->updateTestDeparture(0, 'status', OperationStatusEnum::Cancelled);

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $card = $this->findCard($crawler, '港別テスト運航会社');
        $this->assertStringContainsString('✗ 欠航', $card->text());
        $this->assertCount(1, $card->filter('.status-warning'));
        $this->assertStringNotContainsString('スケジュール変更', $card->text());
    }

    /** 途中の港を出る便の状態がバラけていて、欠航・運休・条件付・遅延が混じれば「スケジュール変更」と出し、会社別ページへリンクする */
    public function testIndexShowsScheduleChangeWhenMidwayStatusesDiffer(): void
    {
        $this->createPortBoardData();
        $this->persistOperationStatus('港別テスト運航会社 下り', 0, OperationStatusEnum::NoService);
        $em    = $this->entityManager();
        $route = $em->getRepository(Route::class)->findOneBy(['name' => '港別テスト運航会社 下り']);
        $port  = $em->getRepository(Port::class)->findOneBy(['name' => '名瀬']);
        $this->assertNotNull($route);
        $this->assertNotNull($port);
        $em->persist($this->makeDeparture($route, $port, new \DateTime('today'), '港別テスト二号', OperationStatusEnum::Cancelled, (new \DateTime('today'))->setTime(9, 0)));
        $em->flush();
        $em->clear();

        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $card = $this->findCard($crawler, '港別テスト運航会社');
        $link = $card->filter('a.route-midway');
        $this->assertCount(1, $link);
        $this->assertSame('▲ スケジュール変更', trim($link->text()));
        $this->assertStringNotContainsString('欠航', $card->text());
        $this->assertStringNotContainsString('便なし', $card->text());
    }

    public function testIndexIsPrivateAndVariesByCookie(): void
    {
        $this->client->request('GET', '/');

        $this->assertTrue($this->client->getResponse()->headers->hasCacheControlDirective('private'));
        $this->assertContains('Cookie', $this->client->getResponse()->getVary());
    }

    /**
     * 下りの寄港順（鹿児島→名瀬→那覇）を持つ2社と、名瀬発の港別ステータスを作る。
     * - 今日: 運航会社が船あり・通常運航（05:50発・翌08:00着）、非運航会社が no_service。鹿児島発は非運航会社の no_service だけ
     * - 3日先: 運航会社が status null（運航予定）
     * - $tomorrowStatus を渡すと、明日の名瀬発に運航会社のその status の行を足す
     * - $direction に上りを渡すと、寄港順を那覇→名瀬→鹿児島にした上りの航路で作る（便は同じく名瀬発）
     */
    private function createPortBoardData(?OperationStatusEnum $tomorrowStatus = null, RouteDirectionEnum $direction = RouteDirectionEnum::Down): void
    {
        $em    = $this->entityManager();
        $ports = [];
        foreach (['鹿児島', '名瀬', '那覇'] as $name) {
            $ports[$name] = $em->getRepository(Port::class)->findOneBy(['name' => $name]);
            $this->assertNotNull($ports[$name], 'ports の初期データがありません（マイグレーションを確認）');
        }

        $operator = (new FerryCompany())->setName('港別テスト運航会社')->setActive(true);
        $other    = (new FerryCompany())->setName('港別テスト非運航会社')->setActive(true);
        $today    = new \DateTime('today');

        $routes = [];
        foreach ([$operator, $other] as $company) {
            $route = (new Route())
                ->setFerryCompany($company)
                ->setName($company->getName() . ($direction === RouteDirectionEnum::Down ? ' 下り' : ' 上り'))
                ->setDirection($direction)
                ->setActive(true);
            $em->persist($route);
            $stops = ['鹿児島', '名瀬', '那覇'];
            foreach ($direction === RouteDirectionEnum::Down ? $stops : array_reverse($stops) as $i => $name) {
                $em->persist((new RouteStop())->setRoute($route)->setPort($ports[$name])->setStopOrder($i + 1));
            }
            $routes[] = $route;
        }

        $em->persist($this->makeDeparture($routes[0], $ports['名瀬'], clone $today, '港別テスト丸', OperationStatusEnum::Operating, (clone $today)->setTime(5, 50))
            ->setScheduledArrivalAt((clone $today)->modify('+1 day')->setTime(8, 0)));
        $em->persist($this->makeDeparture($routes[1], $ports['名瀬'], clone $today, '', OperationStatusEnum::NoService, null));
        $em->persist($this->makeDeparture($routes[1], $ports['鹿児島'], clone $today, '', OperationStatusEnum::NoService, null));
        $em->persist($this->makeDeparture($routes[0], $ports['名瀬'], (clone $today)->modify('+3 days'), '港別テスト丸', null, (clone $today)->modify('+3 days')->setTime(5, 50)));
        if ($tomorrowStatus !== null) {
            $em->persist($this->makeDeparture($routes[0], $ports['名瀬'], (clone $today)->modify('+1 day'), '港別テスト丸', $tomorrowStatus, (clone $today)->modify('+1 day')->setTime(5, 50)));
        }

        $em->persist($other);
        $this->persistCompany($operator);
        $this->createdCompanyIds[] = $other->getId();
    }

    /**
     * createPortBoardData() で作った港別テスト丸の、$daysAhead 日後の行の1項目を書き換える。
     */
    private function updateTestDeparture(int $daysAhead, string $field, mixed $value): void
    {
        $this->entityManager()
            ->createQuery("UPDATE App\\Entity\\DepartureStatus d SET d.{$field} = :value WHERE d.departureDate = :date AND d.shipName = :ship")
            ->setParameter('value', $value)
            ->setParameter('date', (new \DateTime('today'))->modify("+{$daysAhead} days"))
            ->setParameter('ship', '港別テスト丸')
            ->execute();
    }

    /** 港別ステータスの確認時刻を書き換える。$companyName が null なら全部 */
    private function setCheckedAt(?string $companyName, string $checkedAt): void
    {
        $conn = $this->entityManager()->getConnection();
        $time = (new \DateTimeImmutable($checkedAt))->format('Y-m-d H:i:s');
        if ($companyName === null) {
            $conn->executeStatement('UPDATE departure_statuses SET checked_at = ?', [$time]);

            return;
        }
        $conn->executeStatement(
            'UPDATE departure_statuses d JOIN routes r ON r.id = d.route_id JOIN ferry_companies fc ON fc.id = r.ferry_company_id SET d.checked_at = ? WHERE fc.name = ?',
            [$time, $companyName],
        );
    }

    private function companyId(string $name): int
    {
        return $this->entityManager()->getRepository(FerryCompany::class)->findOneBy(['name' => $name])->getId();
    }

    private function persistOperationStatus(string $routeName, int $daysAhead, OperationStatusEnum $status, ?string $detail = null): void
    {
        $em = $this->entityManager();
        $em->persist((new OperationStatus())
            ->setRoute($em->getRepository(Route::class)->findOneBy(['name' => $routeName]))
            ->setStatus($status)
            ->setStatusDetail($detail)
            ->setValidDate((new \DateTime('today'))->modify("+{$daysAhead} days"))
            ->setScrapedAt(new \DateTime())
            ->setSourceUrl('https://example.invalid/test'));
        $em->flush();
        $em->clear();
    }

    private function portId(string $name): int
    {
        return $this->entityManager()->getRepository(Port::class)->findOneBy(['name' => $name])->getId();
    }

    private function makeDeparture(Route $route, Port $port, \DateTime $date, string $ship, ?OperationStatusEnum $status, ?\DateTime $departureAt): DepartureStatus
    {
        return (new DepartureStatus())
            ->setRoute($route)
            ->setPort($port)
            ->setDepartureDate($date)
            ->setShipName($ship)
            ->setStatus($status)
            ->setScheduledDepartureAt($departureAt)
            ->setContentHash(str_repeat('a', 64))
            ->setScrapedAt((new \DateTime('today'))->setTime(6, 0))
            ->setCheckedAt((new \DateTime('today'))->setTime(6, 0));
    }

    /**
     * $dayIndex 番目の日付セクションの、下りの「{$portName}発」の行。
     * テスト DB に他の航路があっても、方向ごとに最初の航路の寄港順になるため、行の有無だけで探す。
     */
    private function findPortRow(Crawler $crawler, int $dayIndex, string $portName): Crawler
    {
        $section = $crawler->filter('section')->eq($dayIndex);
        $row     = $section->filter('.card')->first()->filter('li.port-row')->reduce(
            static fn (Crawler $n) => str_starts_with(trim($n->filter('.fw-bold')->text()), $portName . '発')
        );
        $this->assertCount(1, $row, "{$portName}発の行がありません。");

        return $row;
    }

    /**
     * 公式サイトURL・有効航路1本・本日の運航ステータス（既定は通常運航）を持つ会社を作成する。
     * テストDBが空でもグリッドとカード内部の描画を検証できるようにするため。
     */
    private function createCompanyWithRoute(string $name = 'グリッドテスト会社', OperationStatusEnum $status = OperationStatusEnum::Operating): int
    {
        $company = (new FerryCompany())
            ->setName($name)
            ->setWebsiteUrl('https://example.invalid')
            ->setActive(true);
        $route = (new Route())
            ->setFerryCompany($company)
            ->setName('グリッドテスト航路')
            ->setActive(true);
        $operationStatus = (new OperationStatus())
            ->setRoute($route)
            ->setStatus($status)
            ->setValidDate(new \DateTime('today'))
            ->setScrapedAt(new \DateTime())
            ->setSourceUrl('https://example.invalid/test');

        $em = $this->entityManager();
        $em->persist($route);
        $em->persist($operationStatus);

        return $this->persistCompany($company);
    }

    /**
     * 会社名でカードを1枚に絞り込む。テストDBに既存データがあっても他社のカードを拾わないようにするため。
     */
    private function findCard(Crawler $crawler, string $companyName): Crawler
    {
        $card = $crawler->filter('.card')->reduce(
            static fn (Crawler $node) => $node->filter('.card-header a')->count() > 0
                && trim($node->filter('.card-header a')->first()->text()) === $companyName
        );
        $this->assertCount(1, $card, sprintf('「%s」のカードが描画されていません。', $companyName));

        return $card;
    }

    private function persistCompany(FerryCompany $company): int
    {
        $em = $this->entityManager();
        $em->persist($company);
        $em->flush();

        $companyId                 = $company->getId();
        $this->createdCompanyIds[] = $companyId;

        // リクエストは同じ EntityManager を使う。identity map に残った FerryCompany は
        // routes コレクションが空のまま初期化済みなので、fetch join しても航路が入らない。
        // clear して DB から読み直させる
        $em->clear();

        return $companyId;
    }

    private function entityManager(): EntityManagerInterface
    {
        return static::getContainer()->get(EntityManagerInterface::class);
    }
}
