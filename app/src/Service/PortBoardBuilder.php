<?php

namespace App\Service;

use App\Entity\DepartureStatus;
use App\Entity\Port;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\View\PortBoard;
use App\View\PortBoardDay;
use App\View\PortBoardDirection;
use App\View\PortBoardEntry;
use App\View\PortBoardRow;

/**
 * 港別ページの組み立て（data-model.md の合成ルール1〜5、FR-010・018・019・021）。
 *
 * DB には依存しない。日付 × 方向 × 出発港ごとに、2社分の departure_statuses を1行にまとめる。
 *
 * 1. その (date, direction, port) の行を全社分集める
 * 2. no_service 以外（status が null の運航予定を含む）の行を、それぞれ1エントリにする
 * 3. 2 が0件で、他社運航の目印（operatedByCompany）がある no_service 行があれば、その会社のエントリを作る
 *    （今日以前 → 情報なし、明日以降 → 運航予定）
 * 4. まだ0件で no_service 行があれば「便なし」
 * 5. 行が1件も無ければ「情報なし」
 */
class PortBoardBuilder
{
    /**
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     * @param list<DepartureStatus> $statuses
     */
    public function build(array $boardStops, array $statuses, \DateTimeImmutable $today, int $days): PortBoard
    {
        $today = $today->setTime(0, 0);

        /** @var array<string, list<DepartureStatus>> $grouped */
        $grouped = [];
        foreach ($statuses as $status) {
            $direction = $status->getRoute()?->getDirection();
            if ($direction === null) {
                continue;
            }
            $key             = $this->key($status->getDepartureDate()->format('Y-m-d'), $direction, $status->getPort()->getName());
            $grouped[$key][] = $status;
        }

        $boardDays = [];
        for ($i = 0; $i < $days; ++$i) {
            $date       = $today->modify("+{$i} days");
            $directions = [];
            foreach ($boardStops as $stops) {
                $rows = [];
                foreach ($stops['departurePorts'] as $port) {
                    $key    = $this->key($date->format('Y-m-d'), $stops['direction'], $port->getName());
                    $rows[] = new PortBoardRow($port, $this->entries($grouped[$key] ?? [], $date, $today));
                }
                $directions[] = new PortBoardDirection($stops['direction'], $stops['arrivalPort']->getName(), $rows);
            }
            $boardDays[] = new PortBoardDay($date, $directions);
        }

        return new PortBoard($boardDays);
    }

    /**
     * @param list<DepartureStatus> $statuses
     *
     * @return list<PortBoardEntry>
     */
    private function entries(array $statuses, \DateTimeImmutable $date, \DateTimeImmutable $today): array
    {
        // ルール2: 便がある行（運航予定を含む）
        $services = array_values(array_filter(
            $statuses,
            static fn (DepartureStatus $s) => $s->getStatus() !== OperationStatusEnum::NoService,
        ));
        if ($services !== []) {
            usort($services, static function (DepartureStatus $a, DepartureStatus $b): int {
                return [$a->getScheduledDepartureAt()?->format('Y-m-d H:i:s') ?? '9999', $a->getRoute()->getFerryCompany()->getId()]
                    <=> [$b->getScheduledDepartureAt()?->format('Y-m-d H:i:s') ?? '9999', $b->getRoute()->getFerryCompany()->getId()];
            });

            return array_map(static fn (DepartureStatus $s) => new PortBoardEntry(
                state: $s->getStatus() === null ? DepartureDisplayStateEnum::Scheduled : DepartureDisplayStateEnum::Status,
                status: $s->getStatus(),
                companyName: $s->getRoute()->getFerryCompany()->getName(),
                shipName: $s->getShipName() !== '' ? $s->getShipName() : null,
                departureAt: $s->getScheduledDepartureAt(),
                arrivalAt: $s->getScheduledArrivalAt(),
                detail: $s->getStatusDetail(),
                checkedAt: $s->getCheckedAt(),
                companyId: $s->getRoute()->getFerryCompany()->getId(),
            ), $services);
        }

        // ルール3: 他社運航と分かっている
        foreach ($statuses as $s) {
            $operator = $s->getOperatedByCompany();
            // 無効にした会社は「〇〇／運航予定」として出さない（トップ・/ports の対象外なので）
            if ($operator === null || !$operator->isActive()) {
                continue;
            }

            return [new PortBoardEntry(
                state: $date <= $today ? DepartureDisplayStateEnum::NoInfo : DepartureDisplayStateEnum::Scheduled,
                companyName: $operator->getName(),
                checkedAt: $s->getCheckedAt(),
                companyId: $operator->getId(),
            )];
        }

        // ルール4: 全社 no_service
        if ($statuses !== []) {
            $checkedAt = max(array_map(static fn (DepartureStatus $s) => $s->getCheckedAt(), $statuses));

            return [new PortBoardEntry(state: DepartureDisplayStateEnum::NoService, checkedAt: $checkedAt)];
        }

        // ルール5: 行が無い
        return [new PortBoardEntry(state: DepartureDisplayStateEnum::NoInfo)];
    }

    private function key(string $date, RouteDirectionEnum $direction, string $portName): string
    {
        return $date . '|' . $direction->value . '|' . $portName;
    }
}
