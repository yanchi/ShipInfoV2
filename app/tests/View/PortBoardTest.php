<?php

namespace App\Tests\View;

use App\Entity\Port;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\RouteDirectionEnum;
use App\View\PortBoard;
use App\View\PortBoardDay;
use App\View\PortBoardDirection;
use App\View\PortBoardEntry;
use App\View\PortBoardRow;
use PHPUnit\Framework\TestCase;

class PortBoardTest extends TestCase
{
    public function testCommonCheckedAtWhenAllSameMinute(): void
    {
        $direction = $this->direction(RouteDirectionEnum::Down, [
            $this->row(1, [$this->entry('2026-10-01 06:00:05')]),
            $this->row(2, [$this->entry('2026-10-01 06:00:40'), $this->entry(null)]),
        ]);

        $this->assertSame('2026-10-01 06:00:05', $direction->commonCheckedAt()?->format('Y-m-d H:i:s'));
    }

    public function testCommonCheckedAtIsNullWhenOneDiffers(): void
    {
        $direction = $this->direction(RouteDirectionEnum::Down, [
            $this->row(1, [$this->entry('2026-10-01 06:00')]),
            $this->row(2, [$this->entry('2026-10-01 06:15')]),
        ]);

        $this->assertNull($direction->commonCheckedAt());
    }

    public function testCommonCheckedAtIsNullWithoutCheckedAt(): void
    {
        $direction = $this->direction(RouteDirectionEnum::Down, [$this->row(1, [$this->entry(null)])]);

        $this->assertNull($direction->commonCheckedAt());
    }

    public function testLastCheckedAt(): void
    {
        $board = new PortBoard([
            new PortBoardDay(new \DateTimeImmutable('2026-10-01'), [
                $this->direction(RouteDirectionEnum::Down, [$this->row(1, [$this->entry('2026-10-01 06:00')])]),
            ]),
            new PortBoardDay(new \DateTimeImmutable('2026-10-02'), [
                $this->direction(RouteDirectionEnum::Up, [$this->row(1, [$this->entry('2026-10-01 07:30'), $this->entry(null)])]),
            ]),
        ]);

        $this->assertSame('2026-10-01 07:30', $board->lastCheckedAt()?->format('Y-m-d H:i'));
        $this->assertNull((new PortBoard([]))->lastCheckedAt());
    }

    // ------------------------------------------------------------------

    /** @param list<PortBoardRow> $rows */
    private function direction(RouteDirectionEnum $direction, array $rows): PortBoardDirection
    {
        return new PortBoardDirection($direction, '那覇', $rows);
    }

    /** @param list<PortBoardEntry> $entries */
    private function row(int $portId, array $entries): PortBoardRow
    {
        return new PortBoardRow($this->port($portId), $entries);
    }

    private function entry(?string $checkedAt): PortBoardEntry
    {
        return new PortBoardEntry(
            DepartureDisplayStateEnum::NoService,
            checkedAt: $checkedAt !== null ? new \DateTimeImmutable($checkedAt) : null,
        );
    }

    private function port(int $id): Port
    {
        $port = (new Port())->setName('港' . $id);
        (new \ReflectionProperty($port, 'id'))->setValue($port, $id);

        return $port;
    }
}
