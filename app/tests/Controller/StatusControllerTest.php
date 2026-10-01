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
use Symfony\Component\DomCrawler\Crawler;

class StatusControllerTest extends WebTestCase
{
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
        $this->assertSelectorTextContains('h1', 'ShipInfo');
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
        $this->assertCount(1, $card->filter('.list-group .list-group-item .badge.bg-success'));
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
        for ($i = 0; $i < 4; $i++) {
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
        $this->assertCount(1, $row->filter('.badge.bg-success'));
        $this->assertStringNotContainsString('便なし', $row->text());
        $this->assertStringNotContainsString('港別テスト非運航会社', $row->text());
    }

    public function testPortsShowsScheduledBadge(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $row = $this->findPortRow($crawler, 3, '名瀬');
        $this->assertStringContainsString('運航予定', $row->filter('.badge')->text());
        $this->assertCount(0, $row->filter('.badge.bg-success'));
    }

    public function testPortsShowsCheckedAt(): void
    {
        $this->createPortBoardData();

        $crawler = $this->client->request('GET', '/ports');

        $row      = $this->findPortRow($crawler, 0, '名瀬');
        $expected = (new \DateTimeImmutable('today'))->setTime(6, 0)->format('n/j H:i') . '時点';
        $this->assertStringContainsString($expected, $row->text());
    }

    public function testIndexLinksToPorts(): void
    {
        $crawler = $this->client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertCount(1, $crawler->filter('a[href="/ports"]'));
    }

    /**
     * 下りの寄港順（鹿児島→名瀬→那覇）を持つ2社と、名瀬発の港別ステータスを作る。
     * - 今日: 運航会社が船あり・通常運航（05:50発）、非運航会社が no_service
     * - 3日先: 運航会社が status null（運航予定）
     */
    private function createPortBoardData(): void
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
                ->setName($company->getName() . ' 下り')
                ->setDirection(RouteDirectionEnum::Down)
                ->setActive(true);
            $em->persist($route);
            foreach (['鹿児島', '名瀬', '那覇'] as $i => $name) {
                $em->persist((new RouteStop())->setRoute($route)->setPort($ports[$name])->setStopOrder($i + 1));
            }
            $routes[] = $route;
        }

        $em->persist($this->makeDeparture($routes[0], $ports['名瀬'], (clone $today), '港別テスト丸', OperationStatusEnum::Operating, (clone $today)->setTime(5, 50)));
        $em->persist($this->makeDeparture($routes[1], $ports['名瀬'], (clone $today), '', OperationStatusEnum::NoService, null));
        $em->persist($this->makeDeparture($routes[0], $ports['名瀬'], (clone $today)->modify('+3 days'), '港別テスト丸', null, (clone $today)->modify('+3 days')->setTime(5, 50)));

        $em->persist($other);
        $this->persistCompany($operator);
        $this->createdCompanyIds[] = $other->getId();
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
     * 公式サイトURL・有効航路1本・本日の運航ステータス（通常運航）を持つ会社を作成する。
     * テストDBが空でもグリッドとカード内部の描画を検証できるようにするため。
     */
    private function createCompanyWithRoute(): int
    {
        $company = (new FerryCompany())
            ->setName('グリッドテスト会社')
            ->setWebsiteUrl('https://example.invalid')
            ->setActive(true);
        $route = (new Route())
            ->setFerryCompany($company)
            ->setName('グリッドテスト航路')
            ->setActive(true);
        $status = (new OperationStatus())
            ->setRoute($route)
            ->setStatus(OperationStatusEnum::Operating)
            ->setValidDate(new \DateTime('today'))
            ->setScrapedAt(new \DateTime())
            ->setSourceUrl('https://example.invalid/test');

        $em = $this->entityManager();
        $em->persist($route);
        $em->persist($status);

        return $this->persistCompany($company);
    }

    /**
     * 会社名でカードを1枚に絞り込む。テストDBに既存データがあっても他社のカードを拾わないようにするため。
     */
    private function findCard(Crawler $crawler, string $companyName): Crawler
    {
        $card = $crawler->filter('.card')->reduce(
            static fn (Crawler $node) => trim($node->filter('.card-header a')->first()->text()) === $companyName
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
        return static::getContainer()->get('doctrine')->getManager();
    }
}
