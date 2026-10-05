<?php

namespace App\Tests\Service;

use App\Entity\DepartureStatus;
use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Port;
use App\Entity\Route;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Repository\DepartureStatusRepository;
use App\Repository\OperationStatusRepository;
use App\Service\IrregularServiceCollector;
use PHPUnit\Framework\TestCase;

class IrregularServiceCollectorTest extends TestCase
{
    private IrregularServiceCollector $collector;
    private FerryCompany $company;
    private Route $route;

    protected function setUp(): void
    {
        $this->collector = new IrregularServiceCollector(
            $this->createStub(OperationStatusRepository::class),
            $this->createStub(DepartureStatusRepository::class),
        );
        $this->company = $this->company(1, 'A社');
        $this->route   = $this->route(10, $this->company, RouteDirectionEnum::Down);
    }

    private function company(int $id, string $name): FerryCompany
    {
        $company = (new FerryCompany())->setName($name);
        $this->setId($company, $id);

        return $company;
    }

    private function route(int $id, FerryCompany $company, ?RouteDirectionEnum $direction, string $name = '航路'): Route
    {
        $route = (new Route())->setFerryCompany($company)->setName($name)->setDirection($direction);
        $this->setId($route, $id);

        return $route;
    }

    private function setId(object $entity, int $id): void
    {
        (new \ReflectionProperty($entity, 'id'))->setValue($entity, $id);
    }

    private function operation(Route $route, string $date, OperationStatusEnum $status, ?string $detail = null): OperationStatus
    {
        return (new OperationStatus())
            ->setRoute($route)
            ->setStatus($status)
            ->setStatusDetail($detail)
            ->setValidDate(new \DateTime($date));
    }

    private function departure(
        Route $route,
        string $date,
        string $portName,
        ?OperationStatusEnum $status,
        ?string $time = null,
        string $ship = '',
        ?string $detail = null,
    ): DepartureStatus {
        return (new DepartureStatus())
            ->setRoute($route)
            ->setPort((new Port())->setName($portName))
            ->setDepartureDate(new \DateTime($date))
            ->setShipName($ship)
            ->setStatus($status)
            ->setStatusDetail($detail)
            ->setScheduledDepartureAt($time === null ? null : new \DateTime("$date $time"));
    }

    public function testRouteCancelledWithoutPorts(): void
    {
        $items = $this->collector->build([$this->operation($this->route, '2026-10-07', OperationStatusEnum::Cancelled, '台風接近のため')], []);

        $this->assertCount(1, $items);
        $this->assertSame('欠航', $items[0]->statusText());
        $this->assertSame('台風接近のため', $items[0]->detail());
        $this->assertSame([], $items[0]->ports);
    }

    public function testPortsAreGroupedUnderRouteAndSortedByTimeWithNullLast(): void
    {
        $items = $this->collector->build(
            [$this->operation($this->route, '2026-10-07', OperationStatusEnum::Cancelled)],
            [
                $this->departure($this->route, '2026-10-07', '時刻なし', OperationStatusEnum::Cancelled),
                $this->departure($this->route, '2026-10-07', '与論', OperationStatusEnum::Cancelled, '13:10:00', '船'),
                $this->departure($this->route, '2026-10-07', '名瀬', OperationStatusEnum::Cancelled, '07:00:00', '船', '備考'),
            ],
        );

        $this->assertCount(1, $items);
        $this->assertSame(['名瀬', '与論', '時刻なし'], array_map(static fn ($p) => $p->portName, $items[0]->ports));
        $this->assertSame('備考', $items[0]->ports[0]->detail);
        $this->assertNull($items[0]->ports[2]->shipName);
    }

    public function testNormalRouteWithIrregularPort(): void
    {
        $items = $this->collector->build(
            [$this->operation($this->route, '2026-10-07', OperationStatusEnum::Operating, '無視される備考')],
            [$this->departure($this->route, '2026-10-07', '名瀬', OperationStatusEnum::Cancelled)],
        );

        $this->assertCount(1, $items);
        $this->assertSame('通常運航（途中の港に変更あり）', $items[0]->statusText());
        $this->assertNull($items[0]->detail());
    }

    public function testPortOnlyWhenRouteRowMissingOrNoService(): void
    {
        $port = $this->departure($this->route, '2026-10-07', '名瀬', OperationStatusEnum::Cancelled);

        $missing   = $this->collector->build([], [$port]);
        $noService = $this->collector->build([$this->operation($this->route, '2026-10-07', OperationStatusEnum::NoService)], [$port]);

        $this->assertSame('情報なし（途中の港に変更あり）', $missing[0]->statusText());
        $this->assertSame('情報なし（途中の港に変更あり）', $noService[0]->statusText());
    }

    public function testNothingIrregularYieldsNoItems(): void
    {
        $items = $this->collector->build(
            [
                $this->operation($this->route, '2026-10-07', OperationStatusEnum::Operating),
                $this->operation($this->route, '2026-10-08', OperationStatusEnum::NoService),
            ],
            [
                $this->departure($this->route, '2026-10-07', '名瀬', OperationStatusEnum::Operating),
                $this->departure($this->route, '2026-10-07', '与論', null),
                $this->departure($this->route, '2026-10-07', '本部', OperationStatusEnum::NoService),
            ],
        );

        $this->assertSame([], $items);
    }

    public function testUnknownAndSuspendedLabels(): void
    {
        $other = $this->route(11, $this->company, RouteDirectionEnum::Up);
        $items = $this->collector->build([
            $this->operation($this->route, '2026-10-07', OperationStatusEnum::Unknown),
            $this->operation($other, '2026-10-07', OperationStatusEnum::Suspended),
        ], []);

        $this->assertSame(['不明', '運休'], array_map(static fn ($i) => $i->statusText(), $items));
    }

    public function testSortedByCompanyThenDateThenRoute(): void
    {
        $company2 = $this->company(2, 'B社');
        $route20  = $this->route(20, $company2, RouteDirectionEnum::Down);
        $route11  = $this->route(11, $this->company, RouteDirectionEnum::Up);

        $cancelled = OperationStatusEnum::Cancelled;
        $items     = $this->collector->build([
            $this->operation($route20, '2026-10-06', $cancelled),
            $this->operation($route11, '2026-10-08', $cancelled),
            $this->operation($this->route, '2026-10-08', $cancelled),
            $this->operation($this->route, '2026-10-07', $cancelled),
        ], []);

        $this->assertSame(
            ['1|2026-10-07|10', '1|2026-10-08|10', '1|2026-10-08|11', '2|2026-10-06|20'],
            array_map(static fn ($i) => sprintf('%d|%s|%d', $i->company->getId(), $i->date->format('Y-m-d'), $i->route->getId()), $items),
        );
    }

    public function testDirectionLabelFallsBackToRouteName(): void
    {
        $noDirection = $this->route(12, $this->company, null, '直行便');
        $items       = $this->collector->build([
            $this->operation($this->route, '2026-10-07', OperationStatusEnum::Cancelled),
            $this->operation($noDirection, '2026-10-07', OperationStatusEnum::Cancelled),
        ], []);

        $this->assertSame(['下り（那覇行き）', '直行便'], array_map(static fn ($i) => $i->directionLabel(), $items));
    }
}
