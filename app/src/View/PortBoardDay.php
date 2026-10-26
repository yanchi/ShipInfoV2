<?php

namespace App\View;

use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;

final readonly class PortBoardDay
{
    /**
     * @param list<PortBoardDirection> $directions 下り → 上り
     */
    public function __construct(
        public \DateTimeImmutable $date,
        public array $directions,
    ) {
    }

    /**
     * その会社の便（発表済み・運航予定）がこの日にあるか。$direction を渡すとその方向だけを見る。
     * 航路単位の no_service（始発港を出る便が無い）でも、前日に始発港を出た便が今日途中の港を出ることがあるので、その判定に使う。
     */
    public function hasDeparturesOf(int $companyId, ?RouteDirectionEnum $direction = null): bool
    {
        foreach ($this->directions as $d) {
            if ($direction !== null && $d->direction !== $direction) {
                continue;
            }
            foreach ($d->rows as $row) {
                foreach ($row->entries as $entry) {
                    if ($entry->companyId === $companyId && $entry->isDeparture()) {
                        return true;
                    }
                }
            }
        }

        return false;
    }

    /**
     * その会社の、その方向の始発港（先頭の行）を除いた港を出る便（発表済み・運航予定）。
     *
     * @return list<PortBoardEntry>
     */
    public function midwayDeparturesOf(int $companyId, RouteDirectionEnum $direction): array
    {
        $entries = [];
        foreach ($this->directions as $d) {
            if ($d->direction !== $direction) {
                continue;
            }
            foreach (\array_slice($d->rows, 1) as $row) {
                foreach ($row->entries as $entry) {
                    if ($entry->companyId === $companyId && $entry->isDeparture()) {
                        $entries[] = $entry;
                    }
                }
            }
        }

        return $entries;
    }

    /**
     * その会社の、その方向の臨時便（状態が Extra）のうち、出港時刻がいちばん早いもの。出港済みでも返す。
     */
    public function firstExtraDepartureOf(int $companyId, RouteDirectionEnum $direction): ?PortBoardExtraDeparture
    {
        $first = null;
        foreach ($this->directions as $d) {
            if ($d->direction !== $direction) {
                continue;
            }
            foreach ($d->rows as $row) {
                foreach ($row->entries as $entry) {
                    if (
                        $entry->companyId !== $companyId
                        || $entry->state !== DepartureDisplayStateEnum::Status
                        || $entry->status !== OperationStatusEnum::Extra
                        || $entry->departureAt === null
                    ) {
                        continue;
                    }
                    if ($first === null || $entry->departureAt < $first->departureAt) {
                        $first = new PortBoardExtraDeparture($row->port->getName(), $entry->departureAt);
                    }
                }
            }
        }

        return $first;
    }
}
