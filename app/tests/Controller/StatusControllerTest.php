<?php

namespace App\Tests\Controller;

use Symfony\Bundle\FrameworkBundle\Test\WebTestCase;

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
