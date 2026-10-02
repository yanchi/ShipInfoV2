<?php

namespace App\Tests\Service;

use App\Entity\DepartureStatus;
use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Port;
use App\Entity\Route;
use App\Enum\CompanyDayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Service\CompanyDaysBuilder;
use App\Service\PortBoardBuilder;
use App\View\CompanyDay;
use PHPUnit\Framework\TestCase;

/**
 * 会社別ページの日付ごとの状態（data-model の CompanyDay の state の決め方、research R13）。
 */
class CompanyDaysBuilderTest extends TestCase
{
    private \DateTimeImmutable $today;
    /** @var array<string, Port> */
    private array $ports = [];
    private FerryCompany $marue;
    private FerryCompany $marix;
    /** @var array<string, Route> */
    private array $routes = [];

    protected function setUp(): void
    {
        $this->today = new \DateTimeImmutable('2026-10-01');
        foreach (['鹿児島', '名瀬', '那覇'] as $i => $name) {
            $this->ports[$name] = (new Port())->setName($name);
            $this->setId($this->ports[$name], $i + 1);
        }
        $this->marue = (new FerryCompany())->setName('マルエーフェリー');
        $this->setId($this->marue, 1);
        $this->marix = (new FerryCompany())->setName('マリックスライン');
        $this->setId($this->marix, 2);
        foreach ([[$this->marue, 'marue'], [$this->marix, 'marix']] as [$company, $key]) {
            foreach (RouteDirectionEnum::cases() as $direction) {
                $route = (new Route())->setFerryCompany($company)->setDirection($direction)->setName("{$key} {$direction->value}");
                $this->setId($route, \count($this->routes) + 1);
                $this->routes["{$key}_{$direction->value}"] = $route;
            }
        }
    }

    public function testStatesPerDay(): void
    {
        $days = $this->build(1, [
            // 10/1: マルエーの便あり
            $this->departure('marue_down', '名瀬', '2026-10-01', OperationStatusEnum::Operating),
            // 10/2: マルエーは便なし（マリックスは運航）
            $this->departure('marue_down', '名瀬', '2026-10-02', OperationStatusEnum::NoService),
            $this->departure('marix_down', '名瀬', '2026-10-02', OperationStatusEnum::Operating),
            // 10/3: マリックスの行だけ → マルエーは情報なし
            $this->departure('marix_down', '名瀬', '2026-10-03', OperationStatusEnum::Operating),
            // 10/4: 行なし → 情報なし
        ]);

        $this->assertSame(
            [CompanyDayStateEnum::Services, CompanyDayStateEnum::NoService, CompanyDayStateEnum::NoInfo, CompanyDayStateEnum::NoInfo],
            array_map(static fn (CompanyDay $d) => $d->state, $days),
        );
        $this->assertSame(['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'], array_map(static fn (CompanyDay $d) => $d->date->format('Y-m-d'), $days));
        $this->assertNotNull($days[0]->board);
        $this->assertNull($days[1]->board);
    }

    public function testScheduledCountsAsServices(): void
    {
        $days = $this->build(1, [$this->departure('marue_down', '名瀬', '2026-10-04', null)]);

        $this->assertSame(CompanyDayStateEnum::Services, $days[3]->state);
    }

    /** 他社運航と分かっている日：運航会社は便あり（運航予定）、目印を付けた会社は便なし */
    public function testOperatedByOtherCompany(): void
    {
        $statuses = [$this->departure('marue_down', '名瀬', '2026-10-03', OperationStatusEnum::NoService, $this->marix)];

        $this->assertSame(CompanyDayStateEnum::Services, $this->build(2, $statuses)[2]->state);
        $this->assertSame(CompanyDayStateEnum::NoService, $this->build(1, $statuses)[2]->state);
    }

    public function testRouteSummariesForEachDay(): void
    {
        $summary = $this->operationStatus('marue_down', OperationStatusEnum::Delayed);

        $days = $this->build(1, [], ['2026-10-02' => [$summary]]);

        $this->assertSame([], $days[0]->routeSummaries);
        $this->assertSame([$summary], $days[1]->routeSummaries);
    }

    /** 航路単位では便なしでも、その方向の便が途中の港を出る日は要約行を出さない（tasks T054a） */
    public function testNoServiceSummaryIsHiddenWhenDepartingMidway(): void
    {
        $down = $this->operationStatus('marix_down', OperationStatusEnum::NoService);
        $up   = $this->operationStatus('marix_up', OperationStatusEnum::NoService);

        $days = $this->build(2, [
            $this->departure('marix_down', '名瀬', '2026-10-01', OperationStatusEnum::Operating),
        ], ['2026-10-01' => [$down, $up]]);

        $this->assertSame([$up], $days[0]->routeSummaries);
    }

    // ------------------------------------------------------------------

    /**
     * @param list<DepartureStatus> $statuses
     * @param array<string, list<OperationStatus>> $summaries
     *
     * @return list<CompanyDay>
     */
    private function build(int $companyId, array $statuses, array $summaries = []): array
    {
        $p     = $this->ports;
        $stops = [
            ['direction' => RouteDirectionEnum::Down, 'departurePorts' => [$p['鹿児島'], $p['名瀬']], 'arrivalPort' => $p['那覇']],
            ['direction' => RouteDirectionEnum::Up, 'departurePorts' => [$p['那覇'], $p['名瀬']], 'arrivalPort' => $p['鹿児島']],
        ];
        $board = (new PortBoardBuilder())->build($stops, $statuses, $this->today, 4);

        return (new CompanyDaysBuilder())->build($companyId, $board, $statuses, $summaries);
    }

    private function departure(string $routeKey, string $port, string $date, ?OperationStatusEnum $status, ?FerryCompany $operatedBy = null): DepartureStatus
    {
        return (new DepartureStatus())
            ->setRoute($this->routes[$routeKey])
            ->setPort($this->ports[$port])
            ->setDepartureDate(new \DateTime($date))
            ->setShipName('')
            ->setStatus($status)
            ->setOperatedByCompany($operatedBy)
            ->setCheckedAt(new \DateTime('2026-10-01 06:00'));
    }

    private function operationStatus(string $routeKey, OperationStatusEnum $status): OperationStatus
    {
        return (new OperationStatus())->setRoute($this->routes[$routeKey])->setStatus($status);
    }

    private function setId(object $entity, int $id): void
    {
        (new \ReflectionProperty($entity, 'id'))->setValue($entity, $id);
    }
}
