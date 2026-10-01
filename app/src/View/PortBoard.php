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
