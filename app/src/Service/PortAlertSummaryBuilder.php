<?php

namespace App\Service;

use App\View\PortAlert;
use App\View\PortAlertSummary;
use App\View\PortBoard;
use App\View\PortFilter;

/**
 * 全港のボードから異常（欠航・条件付・遅延・運休）を集め、絞り込み条件で「表示する項目」と「外の件数」に分ける（research R4）。
 */
class PortAlertSummaryBuilder
{
    public function build(PortBoard $fullBoard, PortFilter $filter): PortAlertSummary
    {
        $alerts = [];
        $hidden = 0;
        // ボードは日付 → 方向（下り → 上り）→ 寄港順に並んでいるので、そのまま走査すれば並び順になる
        foreach ($fullBoard->days as $day) {
            foreach ($day->directions as $direction) {
                foreach ($direction->rows as $row) {
                    foreach ($row->entries as $entry) {
                        if (!$entry->isAlert()) {
                            continue;
                        }
                        if (!$filter->matches($direction->direction, $row->port)) {
                            ++$hidden;
                            continue;
                        }
                        $alerts[] = new PortAlert($day->date, $direction->direction, $row->port, $direction->arrivalPortName, $entry);
                    }
                }
            }
        }

        return new PortAlertSummary($alerts, $hidden, !$fullBoard->isEmpty());
    }
}
