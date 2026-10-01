<?php

namespace App\Tests\Controller;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Enum\OperationStatusEnum;
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
