<?php

namespace App\Tests\Controller;

use Symfony\Bundle\FrameworkBundle\Test\WebTestCase;

/** エラーページも V1 のテイスト。DB を読む部品は出さない（specs/7-v1-branding/research.md R7） */
class ErrorPageTest extends WebTestCase
{
    public function testNotFoundPageHasSiteChromeWithoutDbParts(): void
    {
        $client  = static::createClient(['debug' => false]);
        $crawler = $client->request('GET', '/company/999999');

        $this->assertResponseStatusCodeSame(404);
        $this->assertSame('/favicon.svg', $crawler->filter('link[rel="icon"]')->attr('href'));
        $this->assertCount(1, $crawler->filter('.site-header .site-name'));
        $this->assertCount(1, $crawler->filter('footer.site-footer'));
        $this->assertCount(0, $crawler->filter('.site-companies'));
        $this->assertCount(0, $crawler->filter('.site-freshness'));
        $nav = $crawler->filter('.site-header nav')->text();
        $this->assertStringContainsString('トップ', $nav);
        $this->assertStringContainsString('港別', $nav);
        $this->assertStringNotContainsString('各社', $nav);
    }

    public function testNotFoundPageHeadMeta(): void
    {
        $client  = static::createClient(['debug' => false]);
        $crawler = $client->request('GET', '/company/999999');

        $title = $crawler->filter('title')->text();
        $this->assertSame('ページが見つかりません | 鹿児島〜沖縄フェリー運航状況', $title);
        $this->assertSame($title, $crawler->filter('meta[property="og:title"]')->attr('content'));
        foreach (['meta[name="description"]', 'link[rel="canonical"]', 'meta[property="og:description"]', 'meta[property="og:url"]', 'meta[property="og:type"]', 'meta[property="og:site_name"]', 'meta[name="twitter:card"]', 'meta[property="og:image"]', 'meta[property="og:image:type"]', 'meta[property="og:image:width"]', 'meta[property="og:image:height"]', 'meta[property="og:image:alt"]'] as $selector) {
            $this->assertCount(1, $crawler->filter($selector), $selector);
        }
        $this->assertSame('summary_large_image', $crawler->filter('meta[name="twitter:card"]')->attr('content'));
        $html = (string) $client->getResponse()->getContent();
        $this->assertStringNotContainsString('ShipInfo', $html);
        $this->assertStringNotContainsString('googletagmanager.com', $html);
        $this->assertStringNotContainsString('gtag(', $html);
    }
}
