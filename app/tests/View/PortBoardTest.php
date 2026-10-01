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
use App\View\PortFilter;
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

    public function testFilterByPortKeepsThatPortInEachDirection(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(5));

        foreach ($board->days as $day) {
            $this->assertSame(
                ['down' => [5], 'up' => [5]],
                $this->portIdsByDirection($day),
            );
        }
    }

    public function testFilterByPortDropsDirectionWithoutThatPort(): void
    {
        // 鹿児島(1) は下りにしか無い
        $board = $this->sampleBoard()->filter(new PortFilter(1));

        $this->assertSame(['down' => [1]], $this->portIdsByDirection($board->days[0]));
    }

    public function testFilterByDirection(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(direction: RouteDirectionEnum::Up));

        $this->assertSame(['up' => [7, 5, 3]], $this->portIdsByDirection($board->days[0]));
    }

    public function testFilterByPortAndDirection(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(5, RouteDirectionEnum::Down));

        $this->assertSame(['down' => [5]], $this->portIdsByDirection($board->days[1]));
    }

    public function testFilterKeepsAllDays(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(999));

        $this->assertCount(2, $board->days);
        $this->assertSame([], $board->days[0]->directions);
    }

    public function testFilterNoneReturnsSameBoard(): void
    {
        $board = $this->sampleBoard();

        $this->assertEquals($board, $board->filter(PortFilter::none()));
    }

    // ------------------------------------------------------------------

    /** 2日分。下り：1・3・5 → 7、上り：7・5・3 → 1 */
    private function sampleBoard(): PortBoard
    {
        $days = [];
        foreach (['2026-10-01', '2026-10-02'] as $date) {
            $days[] = new PortBoardDay(new \DateTimeImmutable($date), [
                $this->direction(RouteDirectionEnum::Down, array_map(fn (int $id) => $this->row($id, [$this->entry(null)]), [1, 3, 5])),
                $this->direction(RouteDirectionEnum::Up, array_map(fn (int $id) => $this->row($id, [$this->entry(null)]), [7, 5, 3])),
            ]);
        }

        return new PortBoard($days);
    }

    /** @return array<string, list<int>> */
    private function portIdsByDirection(PortBoardDay $day): array
    {
        $result = [];
        foreach ($day->directions as $direction) {
            $result[$direction->direction->value] = array_map(static fn (PortBoardRow $r) => $r->port->getId(), $direction->rows);
        }

        return $result;
    }

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
