<?php

namespace App\Tests\View;

use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\View\PortBoardEntry;
use PHPUnit\Framework\TestCase;

class PortBoardEntryTest extends TestCase
{
    public function testIsAlert(): void
    {
        foreach ([OperationStatusEnum::Cancelled, OperationStatusEnum::Delayed, OperationStatusEnum::Suspended] as $status) {
            $this->assertTrue($this->statusEntry($status)->isAlert(), $status->value);
        }
        foreach ([OperationStatusEnum::Operating, OperationStatusEnum::Unknown, OperationStatusEnum::NoService] as $status) {
            $this->assertFalse($this->statusEntry($status)->isAlert(), $status->value);
        }
        $this->assertFalse((new PortBoardEntry(DepartureDisplayStateEnum::NoService))->isAlert());
        $this->assertFalse((new PortBoardEntry(DepartureDisplayStateEnum::Scheduled))->isAlert());
        $this->assertFalse((new PortBoardEntry(DepartureDisplayStateEnum::NoInfo))->isAlert());
    }

    public function testIsDeparted(): void
    {
        $departure = new \DateTimeImmutable('2026-10-01 05:50');

        $operating = $this->statusEntry(OperationStatusEnum::Operating, $departure);
        $this->assertTrue($operating->isDeparted(new \DateTimeImmutable('2026-10-01 05:51')));
        $this->assertFalse($operating->isDeparted(new \DateTimeImmutable('2026-10-01 05:49')));

        $scheduled = new PortBoardEntry(DepartureDisplayStateEnum::Scheduled, departureAt: $departure);
        $this->assertTrue($scheduled->isDeparted(new \DateTimeImmutable('2026-10-01 06:00')));

        foreach ([OperationStatusEnum::Delayed, OperationStatusEnum::Cancelled, OperationStatusEnum::Suspended] as $status) {
            $this->assertFalse($this->statusEntry($status, $departure)->isDeparted(new \DateTimeImmutable('2026-10-01 06:00')), $status->value);
        }

        $this->assertFalse($this->statusEntry(OperationStatusEnum::Operating)->isDeparted(new \DateTimeImmutable('2026-10-01 06:00')));
    }

    public function testCheckedAtDiffersFrom(): void
    {
        $entry = new PortBoardEntry(DepartureDisplayStateEnum::NoService, checkedAt: new \DateTimeImmutable('2026-10-01 06:00:10'));

        $this->assertFalse($entry->checkedAtDiffersFrom(new \DateTimeImmutable('2026-10-01 06:00:50')));
        $this->assertTrue($entry->checkedAtDiffersFrom(new \DateTimeImmutable('2026-10-01 06:01:00')));
        $this->assertTrue($entry->checkedAtDiffersFrom(null));
        $this->assertFalse((new PortBoardEntry(DepartureDisplayStateEnum::NoInfo))->checkedAtDiffersFrom(new \DateTimeImmutable('2026-10-01 06:00')));
    }

    private function statusEntry(OperationStatusEnum $status, ?\DateTimeImmutable $departureAt = null): PortBoardEntry
    {
        return new PortBoardEntry(DepartureDisplayStateEnum::Status, $status, departureAt: $departureAt);
    }
}
