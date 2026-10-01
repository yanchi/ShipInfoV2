<?php

namespace App\Tests\Service;

use App\Entity\Port;
use App\Enum\RouteDirectionEnum;
use App\Service\PortFilterResolver;
use App\View\PortFilterResolution;
use PHPUnit\Framework\TestCase;
use Symfony\Component\HttpFoundation\Request;

/**
 * specs/5-ui-readability/contracts/http-routes.md の GET /ports の表。
 */
class PortFilterResolverTest extends TestCase
{
    private PortFilterResolver $resolver;

    /** @var list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> */
    private array $boardStops;

    protected function setUp(): void
    {
        $this->resolver = new PortFilterResolver();

        // 鹿児島(1)・名瀬(3)・和泊(5)・那覇(7)
        $p = [];
        foreach ([1 => '鹿児島', 3 => '名瀬', 5 => '和泊', 7 => '那覇'] as $id => $name) {
            $p[$id] = (new Port())->setName($name);
            (new \ReflectionProperty($p[$id], 'id'))->setValue($p[$id], $id);
        }
        $this->boardStops = [
            ['direction' => RouteDirectionEnum::Down, 'departurePorts' => [$p[1], $p[3], $p[5]], 'arrivalPort' => $p[7]],
            ['direction' => RouteDirectionEnum::Up, 'departurePorts' => [$p[7], $p[5], $p[3]], 'arrivalPort' => $p[1]],
        ];
    }

    public function testNoQueryNoCookie(): void
    {
        $r = $this->resolve([]);

        $this->assertFalse($r->filter->isActive());
        $this->assertFalse($r->filter->hasSaved);
        $this->assertNull($r->redirectTo);
        $this->assertNull($r->cookie);
    }

    public function testNoQueryUsesCookie(): void
    {
        $r = $this->resolve([], 'port=5&dir=down');

        $this->assertSame(5, $r->filter->portId);
        $this->assertSame(RouteDirectionEnum::Down, $r->filter->direction);
        $this->assertTrue($r->filter->hasSaved);
        $this->assertNull($r->cookie);
    }

    public function testQueryOverridesCookieWithoutChangingIt(): void
    {
        $r = $this->resolve(['port' => '5', 'dir' => 'down'], 'port=3');

        $this->assertSame(['port' => 5, 'dir' => 'down'], $r->filter->toQuery());
        $this->assertTrue($r->filter->hasSaved);
        $this->assertNull($r->redirectTo);
        $this->assertNull($r->cookie);
    }

    public function testPortAllShowsAllAndKeepsCookie(): void
    {
        $r = $this->resolve(['port' => 'all'], 'port=5');

        $this->assertFalse($r->filter->isActive());
        $this->assertTrue($r->filter->hasSaved);
        $this->assertNull($r->cookie);
    }

    public function testSaveWritesCookieAndRedirects(): void
    {
        $r = $this->resolve(['port' => '5', 'dir' => 'down', 'save' => '1']);

        $this->assertSame('/ports?port=5&dir=down', $r->redirectTo);
        $this->assertNotNull($r->cookie);
        $this->assertSame('port_filter', $r->cookie->getName());
        $this->assertSame('port=5&dir=down', $r->cookie->getValue());
        $this->assertFalse($r->cookie->isCleared());
        $this->assertTrue($r->cookie->isHttpOnly());
        $this->assertSame('lax', $r->cookie->getSameSite());
        $this->assertSame('/', $r->cookie->getPath());
        $this->assertGreaterThan(time() + 364 * 86400, $r->cookie->getExpiresTime());
    }

    public function testSaveWithInvalidPortDoesNotWrite(): void
    {
        $r = $this->resolve(['port' => '999', 'dir' => 'down', 'save' => '1'], 'port=3');

        $this->assertSame('/ports?dir=down', $r->redirectTo);
        $this->assertNull($r->cookie);
    }

    public function testClearRemovesCookieAndRedirects(): void
    {
        $r = $this->resolve(['clear' => '1'], 'port=5');

        $this->assertSame('/ports', $r->redirectTo);
        $this->assertNotNull($r->cookie);
        $this->assertSame('port_filter', $r->cookie->getName());
        $this->assertTrue($r->cookie->isCleared());
    }

    public function testInvalidPortInQueryShowsAllPorts(): void
    {
        $r = $this->resolve(['port' => '999', 'dir' => 'down']);

        $this->assertNull($r->filter->portId);
        $this->assertSame(RouteDirectionEnum::Down, $r->filter->direction);
        $this->assertNull($r->redirectTo);
        $this->assertNull($r->cookie);
    }

    public function testInvalidCookieIsCleared(): void
    {
        foreach (['port=999', 'dir=xxx', 'port=5&dir=xxx', 'garbage'] as $value) {
            $r = $this->resolve([], $value);

            $this->assertFalse($r->filter->isActive(), $value);
            $this->assertFalse($r->filter->hasSaved, $value);
            $this->assertNotNull($r->cookie, $value);
            $this->assertTrue($r->cookie->isCleared(), $value);
        }
    }

    public function testResolveFromCookieIgnoresQuery(): void
    {
        $request = new Request(['port' => '5', 'save' => '1'], [], [], ['port_filter' => 'port=3']);
        $r       = $this->resolver->resolveFromCookie($request, $this->boardStops);

        $this->assertNull($r->redirectTo);
        $this->assertNull($r->cookie);
        $this->assertSame(3, $r->filter->portId);
    }

    public function testResolveFromCookieClearsInvalidCookie(): void
    {
        $request = new Request([], [], [], ['port_filter' => 'port=999']);
        $r       = $this->resolver->resolveFromCookie($request, $this->boardStops);

        $this->assertNull($r->redirectTo);
        $this->assertFalse($r->filter->isActive());
        $this->assertTrue($r->cookie?->isCleared());
    }

    public function testDeparturePortsAreUniqueInDownOrderThenUp(): void
    {
        $names = array_map(static fn (Port $p) => $p->getName(), $this->resolver->departurePorts($this->boardStops));

        $this->assertSame(['鹿児島', '名瀬', '和泊', '那覇'], $names);
    }

    /** @param array<string, string> $query */
    private function resolve(array $query, ?string $cookie = null): PortFilterResolution
    {
        $request = new Request($query, [], [], $cookie !== null ? ['port_filter' => $cookie] : []);

        return $this->resolver->resolve($request, $this->boardStops);
    }
}
