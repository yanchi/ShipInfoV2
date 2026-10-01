<?php

namespace App\View;

final readonly class PortAlertSummary
{
    /**
     * @param list<PortAlert> $alerts 絞り込み条件に合うもの（日付 → 方向 → 寄港順）
     */
    public function __construct(
        public array $alerts,
        /** 絞り込みの外にある異常の件数 */
        public int $hiddenCount,
        /** ボードにデータがあるか。false なら「異常なし」を出さない */
        public bool $hasData,
    ) {
    }
}
