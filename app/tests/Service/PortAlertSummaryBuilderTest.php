<?php

namespace App\Tests\Service;

use App\Entity\Port;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Service\PortAlertSummaryBuilder;
use App\View\PortAlert;
use App\View\PortBoard;
use App\View\PortBoardDay;
use App\View\PortBoardDirection;
use App\View\PortBoardEntry;
use App\View\PortBoardRow;
use App\View\PortFilter;
use PHPUnit\Framework\TestCase;

class PortAlertSummaryBuilderTest extends TestCase
{
    private PortAlertSummaryBuilder $builder;

    /** @var array<int, Port> */
    private array $ports = [];

    protected function setUp(): void
    {
        $this->builder = new PortAlertSummaryBuilder();
        foreach ([1 => '鹿児島', 3 => '名瀬', 5 => '和泊', 7 => '那覇'] as $id => $name) {
            $this->ports[$id] = (new Port())->setName($name);
            (new \ReflectionProperty($this->ports[$id], 'id'))->setValue($this->ports[$id], $id);
        }
    }

    public function testOnlyAlertStatusesAreCollected(): void
    {
        $board = $this->board([
            '2026-10-01' => [
                'down' => [
                    1 => [$this->alertEntry(OperationStatusEnum::Operating), $this->alertEntry(OperationStatusEnum::Cancelled)],
                    3 => [$this->alertEntry(OperationStatusEnum::Delayed)],
                    5 => [$this->alertEntry(OperationStatusEnum::Suspended)],
                ],
                'up' => [
                    7 => [new PortBoardEntry(DepartureDisplayStateEnum::Scheduled)],
                    5 => [new PortBoardEntry(DepartureDisplayStateEnum::NoInfo)],
                    3 => [new PortBoardEntry(DepartureDisplayStateEnum::NoService)],
                ],
            ],
        ]);

        $summary = $this->builder->build($board, PortFilter::none());

        $this->assertSame(
            [OperationStatusEnum::Cancelled, OperationStatusEnum::Delayed, OperationStatusEnum::Suspended],
            array_map(static fn (PortAlert $a) => $a->entry->status, $summary->alerts),
        );
        $this->assertSame(0, $summary->hiddenCount);
        $this->assertTrue($summary->hasData);
    }

    public function testOrderIsDateThenDirectionThenStopOrder(): void
    {
        $board = $this->board([
            '2026-10-01' => [
                'down' => [1 => [$this->alertEntry(OperationStatusEnum::Operating)], 5 => [$this->alertEntry(OperationStatusEnum::Cancelled)]],
                'up'   => [7 => [$this->alertEntry(OperationStatusEnum::Delayed)], 3 => [$this->alertEntry(OperationStatusEnum::Delayed)]],
            ],
            '2026-10-02' => [
                'down' => [1 => [$this->alertEntry(OperationStatusEnum::Cancelled)]],
                'up'   => [7 => [$this->alertEntry(OperationStatusEnum::Operating)]],
            ],
        ]);

        $summary = $this->builder->build($board, PortFilter::none());

        $this->assertSame(
            ['r-2026-10-01-down-5', 'r-2026-10-01-up-7', 'r-2026-10-01-up-3', 'r-2026-10-02-down-1'],
            array_map(static fn (PortAlert $a) => $a->anchor(), $summary->alerts),
        );
        $this->assertSame('那覇', $summary->alerts[0]->arrivalPortName);
    }

    public function testFilterSplitsAlertsAndHiddenCount(): void
    {
        $board = $this->board([
            '2026-10-01' => [
                'down' => [3 => [$this->alertEntry(OperationStatusEnum::Cancelled)], 5 => [$this->alertEntry(OperationStatusEnum::Delayed)]],
                'up'   => [5 => [$this->alertEntry(OperationStatusEnum::Suspended)]],
            ],
        ]);

        $summary = $this->builder->build($board, new PortFilter(5, RouteDirectionEnum::Down));

        $this->assertCount(1, $summary->alerts);
        $this->assertSame('r-2026-10-01-down-5', $summary->alerts[0]->anchor());
        $this->assertSame(2, $summary->hiddenCount);
    }

    public function testNoAlertsWithData(): void
    {
        $board = $this->board(['2026-10-01' => ['down' => [1 => [$this->alertEntry(OperationStatusEnum::Operating)]]]]);

        $summary = $this->builder->build($board, PortFilter::none());

        $this->assertSame([], $summary->alerts);
        $this->assertTrue($summary->hasData);
    }

    public function testEmptyBoardHasNoData(): void
    {
        $summary = $this->builder->build(new PortBoard([new PortBoardDay(new \DateTimeImmutable('2026-10-01'), [])]), PortFilter::none());

        $this->assertSame([], $summary->alerts);
        $this->assertFalse($summary->hasData);
    }

    public function testAnchorFormat(): void
    {
        $alert = new PortAlert(new \DateTimeImmutable('2026-10-02'), RouteDirectionEnum::Down, $this->ports[3], '那覇', $this->alertEntry(OperationStatusEnum::Cancelled));

        $this->assertSame('r-2026-10-02-down-3', $alert->anchor());
    }

    // ------------------------------------------------------------------

    /**
     * @param array<string, array<string, array<int, list<PortBoardEntry>>>> $spec 日付 => 方向 => 港ID => エントリー
     */
    private function board(array $spec): PortBoard
    {
        $days = [];
        foreach ($spec as $date => $directions) {
            $dirs = [];
            foreach ($directions as $dir => $rows) {
                $direction = RouteDirectionEnum::from($dir);
                $dirs[]    = new PortBoardDirection(
                    $direction,
                    $direction === RouteDirectionEnum::Down ? '那覇' : '鹿児島',
                    array_map(fn (int $id, array $entries) => new PortBoardRow($this->ports[$id], $entries), array_keys($rows), $rows),
                );
            }
            $days[] = new PortBoardDay(new \DateTimeImmutable($date), $dirs);
        }

        return new PortBoard($days);
    }

    private function alertEntry(OperationStatusEnum $status): PortBoardEntry
    {
        return new PortBoardEntry(DepartureDisplayStateEnum::Status, $status, companyName: 'テスト会社');
    }
}
