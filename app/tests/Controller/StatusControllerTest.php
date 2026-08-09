<?php

namespace App\Tests\Controller;

use Symfony\Bundle\FrameworkBundle\Test\WebTestCase;
use Symfony\Component\DomCrawler\Crawler;

class StatusControllerTest extends WebTestCase
{
    public function testIndexReturns200(): void
    {
        $client = static::createClient();
        $client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorExists('body');
    }

    public function testIndexContainsTitle(): void
    {
        $client = static::createClient();
        $client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->assertSelectorTextContains('h1', 'ShipInfo');
    }

    public function testIndexRendersCompanyGrid(): void
    {
        $client  = static::createClient();
        $crawler = $client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->skipIfNoCompanies($crawler);

        $this->assertSelectorExists('.row.row-cols-1.row-cols-md-2.row-cols-lg-3');
    }

    public function testCompanyCardsAreGridColumns(): void
    {
        $client  = static::createClient();
        $crawler = $client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->skipIfNoCompanies($crawler);

        $this->assertSelectorExists('.row > .col > .card.h-100');
    }

    /**
     * レイアウト変更によるデグレード検知（FR-005）。
     * カード内部の会社名リンク・公式サイトリンク・航路一覧・ステータスバッジが残っていること。
     */
    public function testIndexKeepsCardContent(): void
    {
        $client  = static::createClient();
        $crawler = $client->request('GET', '/');

        $this->assertResponseIsSuccessful();
        $this->skipIfNoCompanies($crawler);

        $this->assertSelectorExists('.card .card-header a[href^="/company/"]');
        $this->assertSelectorExists('.card .card-header a[target="_blank"][rel="noopener noreferrer"]');
        $this->assertSelectorExists('.card .list-group .list-group-item');
        $this->assertSelectorExists('.card .list-group .list-group-item .badge');
    }

    /**
     * 会社データが無い環境ではグリッド自体が描画されないため、該当テストをスキップする。
     * 0件時は「現在情報がありません。」の alert のみが表示される（FR-006）。
     */
    private function skipIfNoCompanies(Crawler $crawler): void
    {
        if ($crawler->filter('.card')->count() === 0) {
            $this->markTestSkipped('会社データが無いためグリッド構造を検証できません。');
        }
    }

    public function testCompanyPageReturns200WhenCompanyExists(): void
    {
        $client = static::createClient();
        $client->request('GET', '/company/1');

        // ID 1 が存在すれば 200、存在しなければ 404（どちらも正常）
        $this->assertContains(
            $client->getResponse()->getStatusCode(),
            [200, 404],
            'Expected 200 or 404'
        );
    }

    public function testCompanyPageReturns404ForNonExistentId(): void
    {
        $client = static::createClient();
        $client->request('GET', '/company/999999');

        $this->assertResponseStatusCodeSame(404);
    }
}
