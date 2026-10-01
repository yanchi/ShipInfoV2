<?php

namespace App\View;

use App\Enum\RouteDirectionEnum;

final readonly class PortBoardDirection
{
    /**
     * @param list<PortBoardRow> $rows 出発港の行（寄港順。終点は含まない）
     */
    public function __construct(
        public RouteDirectionEnum $direction,
        public string $arrivalPortName,
        public array $rows,
    ) {
    }

    /**
     * 確認時刻を持つエントリーが全部同じ分（Y-m-d H:i）ならその時刻（最初のもの）。無いか違えば null。
     */
    public function commonCheckedAt(): ?\DateTimeInterface
    {
        $common = null;
        foreach ($this->rows as $row) {
            foreach ($row->entries as $entry) {
                if ($entry->checkedAt === null) {
                    continue;
                }
                if ($common === null) {
                    $common = $entry->checkedAt;
                } elseif ($entry->checkedAt->format('Y-m-d H:i') !== $common->format('Y-m-d H:i')) {
                    return null;
                }
            }
        }

        return $common;
    }
}
