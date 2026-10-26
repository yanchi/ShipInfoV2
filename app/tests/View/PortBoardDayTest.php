<?php

namespace App\Tests\View;

use App\Entity\Port;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\View\PortBoardDay;
use App\View\PortBoardDirection;
use App\View\PortBoardEntry;
use App\View\PortBoardRow;
use PHPUnit\Framework\TestCase;

class PortBoardDayTest extends TestCase
{
    public function testHasRegularDeparturesOfCountsOriginRowAndIgnoresExtra(): void
    {
        // 始発港（先頭の行）の臨時便以外の行も数える。途中の港だけ見る midwayDeparturesOf() とは違う
        $day = $this->day([
            $this->row(1, [$this->entry(1, OperationStatusEnum::Extra), $this->entry(2, OperationStatusEnum::Cancelled)]),
            $this->row(3, [$this->entry(1, OperationStatusEnum::Extra)]),
        ]);

        $this->assertFalse($day->hasRegularDeparturesOf(1, RouteDirectionEnum::Down));
        $this->assertTrue($day->hasRegularDeparturesOf(2, RouteDirectionEnum::Down));
    }

    public function testHasRegularDeparturesOfIsTrueForOriginRegularRow(): void
    {
        $day = $this->day([
            $this->row(1, [$this->entry(1, OperationStatusEnum::Extra), $this->entry(1, OperationStatusEnum::Unknown)]),
        ]);

        $this->assertTrue($day->hasRegularDeparturesOf(1, RouteDirectionEnum::Down));
    }

    public function testHasRegularDeparturesOfIsFalseWithoutRowsOrForOtherDirection(): void
    {
        $this->assertFalse($this->day([])->hasRegularDeparturesOf(1, RouteDirectionEnum::Down));

        $day = $this->day([$this->row(1, [$this->entry(1, OperationStatusEnum::Operating)])]);
        $this->assertFalse($day->hasRegularDeparturesOf(1, RouteDirectionEnum::Up));
        $this->assertFalse($day->hasRegularDeparturesOf(9, RouteDirectionEnum::Down));
    }

    public function testHasRegularDeparturesOfIgnoresNoServiceEntries(): void
    {
        $noService = new PortBoardEntry(DepartureDisplayStateEnum::NoService, companyId: 1);
        $day       = $this->day([$this->row(1, [$noService])]);

        $this->assertFalse($day->hasRegularDeparturesOf(1, RouteDirectionEnum::Down));
    }

    /** @param list<PortBoardRow> $rows 下りの行 */
    private function day(array $rows): PortBoardDay
    {
        return new PortBoardDay(new \DateTimeImmutable('2026-09-07'), [
            new PortBoardDirection(RouteDirectionEnum::Down, '那覇', $rows),
        ]);
    }

    /** @param list<PortBoardEntry> $entries */
    private function row(int $portId, array $entries): PortBoardRow
    {
        $port = (new Port())->setName('港' . $portId);
        (new \ReflectionProperty($port, 'id'))->setValue($port, $portId);

        return new PortBoardRow($port, $entries);
    }

    private function entry(int $companyId, OperationStatusEnum $status): PortBoardEntry
    {
        return new PortBoardEntry(
            DepartureDisplayStateEnum::Status,
            $status,
            departureAt: new \DateTimeImmutable('2026-09-07 07:00'),
            companyId: $companyId,
        );
    }
}
