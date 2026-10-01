<?php

namespace App\Tests\View;

use App\Entity\Port;
use App\Enum\RouteDirectionEnum;
use App\View\PortFilter;
use PHPUnit\Framework\TestCase;

class PortFilterTest extends TestCase
{
    public function testNoneIsInactiveAndMatchesEverything(): void
    {
        $filter = PortFilter::none();

        $this->assertFalse($filter->isActive());
        $this->assertFalse($filter->hasSaved);
        $this->assertTrue($filter->matches(RouteDirectionEnum::Down, $this->port(5)));
        $this->assertSame([], $filter->toQuery());
    }

    public function testPortOnly(): void
    {
        $filter = new PortFilter(5);

        $this->assertTrue($filter->isActive());
        $this->assertTrue($filter->matches(RouteDirectionEnum::Down, $this->port(5)));
        $this->assertTrue($filter->matches(RouteDirectionEnum::Up, $this->port(5)));
        $this->assertFalse($filter->matches(RouteDirectionEnum::Down, $this->port(3)));
        $this->assertSame(['port' => 5], $filter->toQuery());
    }

    public function testDirectionOnly(): void
    {
        $filter = new PortFilter(direction: RouteDirectionEnum::Up);

        $this->assertTrue($filter->isActive());
        $this->assertTrue($filter->matches(RouteDirectionEnum::Up, $this->port(3)));
        $this->assertFalse($filter->matches(RouteDirectionEnum::Down, $this->port(3)));
        $this->assertSame(['dir' => 'up'], $filter->toQuery());
    }

    public function testPortAndDirection(): void
    {
        $filter = new PortFilter(5, RouteDirectionEnum::Down);

        $this->assertTrue($filter->matches(RouteDirectionEnum::Down, $this->port(5)));
        $this->assertFalse($filter->matches(RouteDirectionEnum::Up, $this->port(5)));
        $this->assertFalse($filter->matches(RouteDirectionEnum::Down, $this->port(3)));
        $this->assertSame(['port' => 5, 'dir' => 'down'], $filter->toQuery());
    }

    private function port(int $id): Port
    {
        $port = new Port();
        (new \ReflectionProperty($port, 'id'))->setValue($port, $id);

        return $port;
    }
}
