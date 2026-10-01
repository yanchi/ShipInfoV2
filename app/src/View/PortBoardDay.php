<?php

namespace App\View;

use App\Enum\DepartureDisplayStateEnum;
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
                    if ($entry->companyId === $companyId
                        && \in_array($entry->state, [DepartureDisplayStateEnum::Status, DepartureDisplayStateEnum::Scheduled], true)) {
                        return true;
                    }
                }
            }
        }

        return false;
    }
}
