<?php

namespace App\Tests\Controller;

use App\Entity\FerryCompany;
use App\Entity\Port;
use App\Entity\Route;
use App\Entity\RouteStop;
use App\Enum\RouteDirectionEnum;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\KernelBrowser;
use Symfony\Bundle\FrameworkBundle\Test\WebTestCase;

/** V1 の URL の転送・robots.txt・sitemap.xml（specs/7-v1-branding/contracts/http-routes.md） */
class SeoControllerTest extends WebTestCase
{
    private KernelBrowser $client;

    /** @var int[] テスト内で作成した会社ID */
    private array $createdCompanyIds = [];

    protected function setUp(): void
    {
        $this->client = static::createClient();
    }

    protected function tearDown(): void
    {
        if ($this->createdCompanyIds !== []) {
            $em = $this->entityManager();
            $em->createQuery('DELETE FROM App\Entity\RouteStop s WHERE s.route IN (SELECT r.id FROM App\Entity\Route r WHERE r.ferryCompany IN (:ids))')
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

    public function testDetailsTodayRedirectsToPorts(): void
    {
        $this->client->request('GET', '/details/today');
        $this->assertResponseStatusCodeSame(301);
        $this->assertSame('http://localhost/ports', $this->location());

        $this->client->request('GET', '/details/today?foo=1');
        $this->assertResponseStatusCodeSame(301);
        $this->assertSame('http://localhost/ports', $this->location());
    }

    public function testRobotsTxt(): void
    {
        $this->client->request('GET', '/robots.txt');

        $this->assertResponseIsSuccessful();
        $this->assertSame('text/plain; charset=UTF-8', $this->client->getResponse()->headers->get('Content-Type'));
        $body = (string) $this->client->getResponse()->getContent();
        $this->assertStringContainsString('User-agent: *', $body);
        $this->assertStringContainsString('Allow: /', $body);
        $this->assertStringContainsString('Sitemap: http://localhost/sitemap.xml', $body);
        $this->assertStringNotContainsString('Disallow', $body);
    }

    public function testSitemapXml(): void
    {
        $active   = $this->persistCompany('サイトマップ有効会社', true);
        $inactive = $this->persistCompany('サイトマップ無効会社', false);

        $this->client->request('GET', '/sitemap.xml');

        $this->assertResponseIsSuccessful();
        $this->assertSame('application/xml; charset=UTF-8', $this->client->getResponse()->headers->get('Content-Type'));
        $xml = new \SimpleXMLElement((string) $this->client->getResponse()->getContent());
        $xml->registerXPathNamespace('s', 'http://www.sitemaps.org/schemas/sitemap/0.9');

        $urls = [];
        foreach ($xml->xpath('//s:url') ?: [] as $url) {
            $children                      = $url->children('http://www.sitemaps.org/schemas/sitemap/0.9');
            $urls[(string) $children->loc] = [(string) $children->changefreq, (string) $children->priority];
        }

        $this->assertSame(['hourly', '1.0'], $urls['http://localhost/'] ?? null);
        $this->assertSame(['hourly', '0.9'], $urls['http://localhost/ports'] ?? null);
        $this->assertSame(['hourly', '0.8'], $urls["http://localhost/company/{$active}"] ?? null);
        $this->assertArrayNotHasKey("http://localhost/company/{$inactive}", $urls);
    }

    /** 港のページが、出発港（終点だけの港を除く）の数だけ載る */
    public function testSitemapListsPortPages(): void
    {
        $this->persistRoute();

        $this->client->request('GET', '/sitemap.xml');

        $xml = new \SimpleXMLElement((string) $this->client->getResponse()->getContent());
        $xml->registerXPathNamespace('s', 'http://www.sitemaps.org/schemas/sitemap/0.9');
        $urls = [];
        foreach ($xml->xpath('//s:url') ?: [] as $url) {
            $children                      = $url->children('http://www.sitemaps.org/schemas/sitemap/0.9');
            $urls[(string) $children->loc] = (string) $children->priority;
        }

        $this->assertSame('0.9', $urls['http://localhost/ports/kagoshima'] ?? null);
        $this->assertSame('0.9', $urls['http://localhost/ports/naze'] ?? null);
        $this->assertArrayNotHasKey('http://localhost/ports/naha', $urls);
    }

    private function location(): string
    {
        return (string) $this->client->getResponse()->headers->get('Location');
    }

    /** 鹿児島→名瀬→那覇の下りの航路を作る（会社ごと tearDown で消える） */
    private function persistRoute(): void
    {
        $em      = $this->entityManager();
        $company = (new FerryCompany())->setName('サイトマップ港会社')->setActive(true);
        $route   = (new Route())->setFerryCompany($company)->setName('サイトマップ港航路')->setDirection(RouteDirectionEnum::Down)->setActive(true);
        $em->persist($route);
        foreach (['鹿児島', '名瀬', '那覇'] as $i => $name) {
            $port = $em->getRepository(Port::class)->findOneBy(['name' => $name]);
            $em->persist((new RouteStop())->setRoute($route)->setPort($port)->setStopOrder($i + 1));
        }
        $em->persist($company);
        $em->flush();
        $this->createdCompanyIds[] = $company->getId();
        $em->clear();
    }

    private function persistCompany(string $name, bool $active): int
    {
        $company = (new FerryCompany())->setName($name)->setActive($active);
        $em      = $this->entityManager();
        $em->persist($company);
        $em->flush();
        $this->createdCompanyIds[] = $company->getId();
        $em->clear();

        return $company->getId();
    }

    private function entityManager(): EntityManagerInterface
    {
        return static::getContainer()->get(EntityManagerInterface::class);
    }
}
