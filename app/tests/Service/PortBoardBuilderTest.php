<?php

namespace App\Tests\Service;

use App\Entity\DepartureStatus;
use App\Entity\FerryCompany;
use App\Entity\Port;
use App\Entity\Route;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Service\PortBoardBuilder;
use App\View\PortBoardEntry;
use App\View\PortBoardRow;
use PHPUnit\Framework\TestCase;

/**
 * data-model.md の合成ルール1〜5 と US1 のシナリオ。
 */
class PortBoardBuilderTest extends TestCase
{
    private PortBoardBuilder $builder;
    private \DateTimeImmutable $today;

    /** @var array<string, Port> */
    private array $ports = [];
    private FerryCompany $marue;
    private FerryCompany $marix;
    /** @var array<string, Route> */
    private array $routes = [];

    protected function setUp(): void
    {
        $this->builder = new PortBoardBuilder();
        $this->today   = new \DateTimeImmutable('2026-10-01');

        foreach (['鹿児島', '名瀬', '亀徳', '和泊', '与論', '本部', '那覇'] as $i => $name) {
            $port = (new Port())->setName($name);
            $this->setId($port, $i + 1);
            $this->ports[$name] = $port;
        }

        $this->marue = (new FerryCompany())->setName('マルエーフェリー');
        $this->setId($this->marue, 1);
        $this->marix = (new FerryCompany())->setName('マリックスライン');
        $this->setId($this->marix, 2);

        foreach ([[$this->marue, 'marue'], [$this->marix, 'marix']] as [$company, $key]) {
            foreach (RouteDirectionEnum::cases() as $direction) {
                $this->routes[$key . '_' . $direction->value] = (new Route())
                    ->setFerryCompany($company)
                    ->setDirection($direction);
            }
        }
    }

    public function testOnlyOperatingCompanyEntryIsShown(): void
    {
        // シナリオ1: マルエー運航、マリックスは便なし → マルエーの1行だけ
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-01', OperationStatusEnum::Operating, 'フェリーあけぼの', '2026-10-01 05:50'),
            $this->departure('marix_down', '名瀬', '2026-10-01', OperationStatusEnum::NoService),
        ]);

        $entries = $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertCount(1, $entries);
        $this->assertSame(DepartureDisplayStateEnum::Status, $entries[0]->state);
        $this->assertSame(OperationStatusEnum::Operating, $entries[0]->status);
        $this->assertSame('マルエーフェリー', $entries[0]->companyName);
        $this->assertSame('フェリーあけぼの', $entries[0]->shipName);
        $this->assertSame('05:50', $entries[0]->departureAt->format('H:i'));
    }

    public function testBothNoServiceShowsNoService(): void
    {
        // シナリオ2
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-01', OperationStatusEnum::NoService),
            $this->departure('marix_down', '名瀬', '2026-10-01', OperationStatusEnum::NoService),
        ]);

        $entries = $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertCount(1, $entries);
        $this->assertSame(DepartureDisplayStateEnum::NoService, $entries[0]->state);
        $this->assertNull($entries[0]->companyName);
    }

    public function testBothCompaniesWithServiceShowTwoEntries(): void
    {
        // シナリオ3（FR-019）
        $board = $this->build([
            $this->departure('marix_down', '名瀬', '2026-10-01', OperationStatusEnum::Delayed, 'クイーンコーラルプラス', '2026-10-01 07:00'),
            $this->departure('marue_down', '名瀬', '2026-10-01', OperationStatusEnum::Operating, 'フェリーあけぼの', '2026-10-01 05:50'),
        ]);

        $entries = $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertCount(2, $entries);
        $this->assertSame(['マルエーフェリー', 'マリックスライン'], array_map(static fn (PortBoardEntry $e) => $e->companyName, $entries));
    }

    public function testOperatedByOtherCompanyTodayIsNoInfo(): void
    {
        // シナリオ4（FR-018）: 当日、マリックス運航と分かっているがマリックスの行が無い
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-01', OperationStatusEnum::NoService, operatedBy: $this->marix),
        ]);

        $entries = $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertCount(1, $entries);
        $this->assertSame(DepartureDisplayStateEnum::NoInfo, $entries[0]->state);
        $this->assertSame('マリックスライン', $entries[0]->companyName);
    }

    public function testOperatedByOtherCompanyFutureIsScheduled(): void
    {
        // シナリオ7（FR-021）
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-03', OperationStatusEnum::NoService, operatedBy: $this->marix),
        ]);

        $entries = $this->row($board, 2, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertSame(DepartureDisplayStateEnum::Scheduled, $entries[0]->state);
        $this->assertSame('マリックスライン', $entries[0]->companyName);
    }

    public function testInactiveOperatorIsTreatedAsNoService(): void
    {
        $this->marix->setActive(false);
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-03', OperationStatusEnum::NoService, operatedBy: $this->marix),
        ]);

        $entries = $this->row($board, 2, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertSame(DepartureDisplayStateEnum::NoService, $entries[0]->state);
        $this->assertNull($entries[0]->companyName);
    }

    public function testOperatedByIsIgnoredWhenOperatorRowExists(): void
    {
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-01', OperationStatusEnum::NoService, operatedBy: $this->marix),
            $this->departure('marix_down', '名瀬', '2026-10-01', OperationStatusEnum::Cancelled, 'クイーンコーラルクロス'),
        ]);

        $entries = $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertCount(1, $entries);
        $this->assertSame(OperationStatusEnum::Cancelled, $entries[0]->status);
    }

    public function testNullStatusIsScheduled(): void
    {
        // シナリオ6
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-10-04', null, 'フェリーあけぼの', '2026-10-04 05:50'),
        ]);

        $entries = $this->row($board, 3, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertSame(DepartureDisplayStateEnum::Scheduled, $entries[0]->state);
        $this->assertSame('フェリーあけぼの', $entries[0]->shipName);
    }

    public function testNoRowsIsNoInfo(): void
    {
        $board   = $this->build([]);
        $entries = $this->row($board, 0, RouteDirectionEnum::Up, '那覇')->entries;
        $this->assertCount(1, $entries);
        $this->assertSame(DepartureDisplayStateEnum::NoInfo, $entries[0]->state);
        $this->assertNull($entries[0]->companyName);
    }

    public function testPortsAreInStopOrderWithoutTerminal(): void
    {
        $board = $this->build([]);
        $day   = $board->days[0];

        $this->assertSame([RouteDirectionEnum::Down, RouteDirectionEnum::Up], array_map(static fn ($d) => $d->direction, $day->directions));
        $this->assertSame(['鹿児島', '名瀬', '亀徳', '和泊', '与論', '本部'], $this->portNames($day->directions[0]->rows));
        $this->assertSame('那覇', $day->directions[0]->arrivalPortName);
        $this->assertSame(['那覇', '本部', '与論', '和泊', '亀徳', '名瀬'], $this->portNames($day->directions[1]->rows));
        $this->assertSame('鹿児島', $day->directions[1]->arrivalPortName);
    }

    public function testOnlyTodayToThreeDaysAhead(): void
    {
        // シナリオ5
        $board = $this->build([
            $this->departure('marue_down', '名瀬', '2026-09-30', OperationStatusEnum::Cancelled, 'フェリーあけぼの'),
        ]);

        $this->assertSame(
            ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'],
            array_map(static fn ($d) => $d->date->format('Y-m-d'), $board->days),
        );
        // 前日の行は今日に混ざらない
        $entries = $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries;
        $this->assertSame(DepartureDisplayStateEnum::NoInfo, $entries[0]->state);
    }

    public function testDirectionsAreNotMixed(): void
    {
        $board = $this->build([
            $this->departure('marue_up', '名瀬', '2026-10-01', OperationStatusEnum::Operating, 'フェリー波之上'),
        ]);

        $this->assertSame(DepartureDisplayStateEnum::NoInfo, $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries[0]->state);
        $this->assertSame(DepartureDisplayStateEnum::Status, $this->row($board, 0, RouteDirectionEnum::Up, '名瀬')->entries[0]->state);
    }

    public function testEmptyStopsGivesEmptyBoard(): void
    {
        $board = $this->builder->build([], [], $this->today, 4);
        $this->assertTrue($board->isEmpty());
    }

    public function testArrivalText(): void
    {
        $day   = new \DateTimeImmutable('2026-10-01');
        $entry = fn (string $dep, string $arr) => new PortBoardEntry(
            state: DepartureDisplayStateEnum::Status,
            departureAt: new \DateTimeImmutable($dep),
            arrivalAt: new \DateTimeImmutable($arr),
        );

        $this->assertSame('19:00着', $entry('2026-10-01 05:50', '2026-10-01 19:00')->arrivalText($day));
        $this->assertSame('翌19:00着', $entry('2026-10-01 18:00', '2026-10-02 19:00')->arrivalText($day));
        $this->assertSame('10/3 08:00着', $entry('2026-10-01 18:00', '2026-10-03 08:00')->arrivalText($day));
    }

    public function testCompanyIdIsSetForServiceAndOperatedByEntries(): void
    {
        $board = $this->build([
            // ルール2
            $this->departure('marix_down', '名瀬', '2026-10-01', OperationStatusEnum::Operating, 'クイーンコーラルプラス'),
            // ルール3
            $this->departure('marue_down', '和泊', '2026-10-02', OperationStatusEnum::NoService, operatedBy: $this->marix),
            // ルール4
            $this->departure('marue_down', '与論', '2026-10-01', OperationStatusEnum::NoService),
        ]);

        $this->assertSame(2, $this->row($board, 0, RouteDirectionEnum::Down, '名瀬')->entries[0]->companyId);
        $this->assertSame(2, $this->row($board, 1, RouteDirectionEnum::Down, '和泊')->entries[0]->companyId);
        $this->assertNull($this->row($board, 0, RouteDirectionEnum::Down, '与論')->entries[0]->companyId);
        // ルール5
        $this->assertNull($this->row($board, 0, RouteDirectionEnum::Up, '那覇')->entries[0]->companyId);
    }

    // ------------------------------------------------------------------

    /** @param list<DepartureStatus> $statuses */
    private function build(array $statuses): \App\View\PortBoard
    {
        $p     = $this->ports;
        $stops = [
            [
                'direction'      => RouteDirectionEnum::Down,
                'departurePorts' => [$p['鹿児島'], $p['名瀬'], $p['亀徳'], $p['和泊'], $p['与論'], $p['本部']],
                'arrivalPort'    => $p['那覇'],
            ],
            [
                'direction'      => RouteDirectionEnum::Up,
                'departurePorts' => [$p['那覇'], $p['本部'], $p['与論'], $p['和泊'], $p['亀徳'], $p['名瀬']],
                'arrivalPort'    => $p['鹿児島'],
            ],
        ];

        return $this->builder->build($stops, $statuses, $this->today, 4);
    }

    private function departure(
        string $routeKey,
        string $portName,
        string $date,
        ?OperationStatusEnum $status,
        string $shipName = '',
        ?string $departureAt = null,
        ?FerryCompany $operatedBy = null,
    ): DepartureStatus {
        return (new DepartureStatus())
            ->setRoute($this->routes[$routeKey])
            ->setPort($this->ports[$portName])
            ->setDepartureDate(new \DateTime($date))
            ->setShipName($shipName)
            ->setStatus($status)
            ->setScheduledDepartureAt($departureAt !== null ? new \DateTime($departureAt) : null)
            ->setOperatedByCompany($operatedBy)
            ->setCheckedAt(new \DateTime('2026-10-01 06:00'));
    }

    private function row(\App\View\PortBoard $board, int $dayIndex, RouteDirectionEnum $direction, string $portName): PortBoardRow
    {
        foreach ($board->days[$dayIndex]->directions as $d) {
            if ($d->direction !== $direction) {
                continue;
            }
            foreach ($d->rows as $row) {
                if ($row->port->getName() === $portName) {
                    return $row;
                }
            }
        }
        $this->fail("row not found: {$dayIndex} {$direction->value} {$portName}");
    }

    /**
     * @param list<PortBoardRow> $rows
     *
     * @return list<string>
     */
    private function portNames(array $rows): array
    {
        return array_map(static fn (PortBoardRow $r) => $r->port->getName(), $rows);
    }

    private function setId(object $entity, int $id): void
    {
        (new \ReflectionProperty($entity, 'id'))->setValue($entity, $id);
    }
}
