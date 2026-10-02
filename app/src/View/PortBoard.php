<?php

namespace App\View;

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
