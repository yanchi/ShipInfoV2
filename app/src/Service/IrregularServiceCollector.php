<?php

namespace App\Service;

use App\Entity\DepartureStatus;
use App\Entity\OperationStatus;
use App\Repository\DepartureStatusRepository;
use App\Repository\OperationStatusRepository;
use App\View\IrregularPort;
use App\View\IrregularService;

/**
 * 通知メールに載せる便を集める。サイトのボードと同じ範囲・条件で、(航路, 日付) ごとに1件にまとめる。
 * build() は DB に依存しない。
 */
class IrregularServiceCollector
{
    public function __construct(
        private readonly OperationStatusRepository $operationStatusRepository,
        private readonly DepartureStatusRepository $departureStatusRepository,
    ) {
    }

    /**
     * @return list<IrregularService>
     */
    public function collect(\DateTimeImmutable $today): array
    {
        return $this->build(
            $this->operationStatusRepository->findLatestBetween($today, PortBoardBuilder::DAYS),
            $this->departureStatusRepository->findIrregularBetween($today, PortBoardBuilder::DAYS),
        );
    }

    /**
     * @param list<OperationStatus> $operationStatuses 航路×日付の最新行（全状態）
     * @param list<DepartureStatus> $departureStatuses 港ごとの行
     *
     * @return list<IrregularService> 会社 ID → 日付 → 航路 ID の順
     */
    public function build(array $operationStatuses, array $departureStatuses): array
    {
        /** @var array<string, OperationStatus> $routeStatuses */
        $routeStatuses = [];
        foreach ($operationStatuses as $operationStatus) {
            $route = $operationStatus->getRoute();
            if ($route === null) {
                continue;
            }
            $routeStatuses[$this->key((int) $route->getId(), $operationStatus->getValidDate())] = $operationStatus;
        }

        /** @var array<string, list<DepartureStatus>> $portRows */
        $portRows = [];
        foreach ($departureStatuses as $departureStatus) {
            $route  = $departureStatus->getRoute();
            $status = $departureStatus->getStatus();
            if ($route === null || $status === null || !$status->isIrregular()) {
                continue;
            }
            $portRows[$this->key((int) $route->getId(), $departureStatus->getDepartureDate())][] = $departureStatus;
        }

        $items = [];
        foreach (array_unique([...array_keys($routeStatuses), ...array_keys($portRows)]) as $key) {
            $routeStatus = $routeStatuses[$key] ?? null;
            $ports       = $this->buildPorts($portRows[$key] ?? []);

            $first = $routeStatus ?? ($portRows[$key][0] ?? null);
            $route = $first?->getRoute();
            if ($first === null || $route === null) {
                continue;
            }
            $company = $route->getFerryCompany();
            $date    = $first instanceof OperationStatus ? $first->getValidDate() : $first->getDepartureDate();
            if ($company === null || $date === null) {
                continue;
            }

            $item = new IrregularService($company, $route, \DateTimeImmutable::createFromInterface($date), $routeStatus, $ports);
            if ($item->isRouteIrregular() || $ports !== []) {
                $items[] = $item;
            }
        }

        usort($items, static fn (IrregularService $a, IrregularService $b): int => [
            (int) $a->company->getId(),
            $a->date->format('Y-m-d'),
            (int) $a->route->getId(),
        ] <=> [
            (int) $b->company->getId(),
            $b->date->format('Y-m-d'),
            (int) $b->route->getId(),
        ]);

        return $items;
    }

    private function key(int $routeId, ?\DateTimeInterface $date): string
    {
        return $routeId . '|' . ($date?->format('Y-m-d') ?? '');
    }

    /**
     * @param list<DepartureStatus> $rows
     *
     * @return list<IrregularPort>
     */
    private function buildPorts(array $rows): array
    {
        usort($rows, static function (DepartureStatus $a, DepartureStatus $b): int {
            $at = $a->getScheduledDepartureAt();
            $bt = $b->getScheduledDepartureAt();
            if ($at === null || $bt === null) {
                return ($at === null) <=> ($bt === null);
            }

            return $at <=> $bt;
        });

        $ports = [];
        foreach ($rows as $row) {
            $status = $row->getStatus();
            $port   = $row->getPort();
            if ($status === null || $port === null) {
                continue;
            }
            $shipName = trim($row->getShipName());
            $detail   = trim((string) $row->getStatusDetail());

            $ports[] = new IrregularPort(
                $port->getName(),
                $shipName === '' ? null : $shipName,
                $row->getScheduledDepartureAt(),
                $status,
                $detail === '' ? null : $detail,
            );
        }

        return $ports;
    }
}
