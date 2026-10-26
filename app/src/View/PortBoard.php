<?php

namespace App\View;

use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;

/**
 * 港別運航情報ページのビューモデル（今日〜n日先）。
 */
final readonly class PortBoard
{
    /**
     * @param list<PortBoardDay> $days
     */
    public function __construct(
        public array $days,
    ) {
    }

    /** 港マスタや寄港順が無くて、表示できる行が1つも無い */
    public function isEmpty(): bool
    {
        foreach ($this->days as $day) {
            if ($day->directions !== []) {
                return false;
            }
        }

        return true;
    }

    /**
     * 絞り込み条件に合う方向・行だけを残した新しいボード。行が無くなった方向は落とし、日付は全部残す。
     */
    public function filter(PortFilter $filter): self
    {
        if (!$filter->isActive()) {
            return $this;
        }

        $days = [];
        foreach ($this->days as $day) {
            $directions = [];
            foreach ($day->directions as $direction) {
                $rows = array_values(array_filter(
                    $direction->rows,
                    static fn (PortBoardRow $row) => $filter->matches($direction->direction, $row->port),
                ));
                if ($rows !== []) {
                    $directions[] = new PortBoardDirection($direction->direction, $direction->arrivalPortName, $rows);
                }
            }
            $days[] = new PortBoardDay($day->date, $directions);
        }

        return new self($days);
    }

    /**
     * その会社の便（発表済み・運航予定）のエントリーだけを残した新しいボード（research R13）。
     * エントリーが無くなった行、行が無くなった方向は落とし、日付は全部残す。
     */
    public function forCompany(int $companyId): self
    {
        $days = [];
        foreach ($this->days as $day) {
            $directions = [];
            foreach ($day->directions as $direction) {
                $rows = [];
                foreach ($direction->rows as $row) {
                    $entries = array_values(array_filter(
                        $row->entries,
                        static fn (PortBoardEntry $e) => $e->companyId === $companyId && $e->isDeparture(),
                    ));
                    if ($entries !== []) {
                        $rows[] = new PortBoardRow($row->port, $entries);
                    }
                }
                if ($rows !== []) {
                    $directions[] = new PortBoardDirection($direction->direction, $direction->arrivalPortName, $rows);
                }
            }
            $days[] = new PortBoardDay($day->date, $directions);
        }

        return new self($days);
    }

    /**
     * その会社の、その方向の、今日を出る臨時便の運航のどれかに抜港があるか（15-extra-voyage-badge FR-004）。
     *
     * 臨時便は寄らない港の行を作らない（12 の FR-006・13 の FR-003）ので、運航の最初と最後の港のあいだで、
     * 同じ船の寄る行（isCalling）が無い港を抜港とみなす。
     * - 同じ運航の臨時便は、船名と到着予定（終点への到着）が同じ。船名か到着予定が無いものは、まとめず1つで1回の運航にする
     * - 前日に始発港を出た運航は、ボードに前日の行が無いので、今日の最初の港から見る
     * - 同じ船が同じ日に別の運航でそのあいだの港に寄ると、寄港に数える（抜港を見落とす。1日に2回出た例は無いので割り切り）
     * - 港の並び（行の添字）は、日付が違っても同じとして扱う
     */
    public function extraSkipsPortsOf(int $companyId, RouteDirectionEnum $direction): bool
    {
        /** @var array<string, array{ship: string, startsToday: bool, minPosition: int, maxPosition: int, minDay: int, maxDay: int}> $voyages */
        $voyages = [];
        foreach ($this->days as $dayIndex => $day) {
            foreach ($day->directions as $d) {
                if ($d->direction !== $direction) {
                    continue;
                }
                foreach ($d->rows as $position => $row) {
                    foreach ($row->entries as $entry) {
                        if (
                            $entry->companyId !== $companyId
                            || $entry->state !== DepartureDisplayStateEnum::Status
                            || $entry->status !== OperationStatusEnum::Extra
                            || $entry->departureAt === null
                        ) {
                            continue;
                        }
                        $ship = (string) $entry->shipName;
                        $key  = $ship === '' || $entry->arrivalAt === null
                            ? "single:{$dayIndex}:{$position}:" . \count($voyages)
                            : $ship . '|' . $entry->arrivalAt->format('Y-m-d H:i');
                        $voyage = $voyages[$key] ?? ['ship' => $ship, 'startsToday' => false, 'minPosition' => $position, 'maxPosition' => $position, 'minDay' => $dayIndex, 'maxDay' => $dayIndex];

                        $voyages[$key] = [
                            'ship'        => $ship,
                            'startsToday' => $voyage['startsToday'] || $dayIndex === 0,
                            'minPosition' => min($voyage['minPosition'], $position),
                            'maxPosition' => max($voyage['maxPosition'], $position),
                            'minDay'      => min($voyage['minDay'], $dayIndex),
                            'maxDay'      => max($voyage['maxDay'], $dayIndex),
                        ];
                    }
                }
            }
        }

        foreach ($voyages as $voyage) {
            if (!$voyage['startsToday'] || $voyage['ship'] === '') {
                continue;
            }
            for ($position = $voyage['minPosition'] + 1; $position < $voyage['maxPosition']; ++$position) {
                if (!$this->callsAt($companyId, $direction, $voyage['ship'], $position, $voyage['minDay'], $voyage['maxDay'])) {
                    return true;
                }
            }
        }

        return false;
    }

    /** 日付の範囲（ボードの日の添字）で、その港の行に同じ会社・同じ船の寄る便があるか */
    private function callsAt(int $companyId, RouteDirectionEnum $direction, string $ship, int $position, int $fromDay, int $toDay): bool
    {
        for ($dayIndex = $fromDay; $dayIndex <= $toDay; ++$dayIndex) {
            foreach ($this->days[$dayIndex]->directions as $d) {
                if ($d->direction !== $direction || !isset($d->rows[$position])) {
                    continue;
                }
                foreach ($d->rows[$position]->entries as $entry) {
                    if ($entry->companyId === $companyId && $entry->shipName === $ship && $entry->isCalling()) {
                        return true;
                    }
                }
            }
        }

        return false;
    }

    /** ボード内の最大の確認時刻 */
    public function lastCheckedAt(): ?\DateTimeInterface
    {
        $last = null;
        foreach ($this->days as $day) {
            foreach ($day->directions as $direction) {
                foreach ($direction->rows as $row) {
                    foreach ($row->entries as $entry) {
                        if ($entry->checkedAt !== null && ($last === null || $entry->checkedAt > $last)) {
                            $last = $entry->checkedAt;
                        }
                    }
                }
            }
        }

        return $last;
    }
}
