<?php

namespace App\View;

/**
 * トップの会社カードに出す臨時便の1行（「◆ 臨時便 鹿児島 16:00発」）の港と出港時刻。
 */
final readonly class PortBoardExtraDeparture
{
    public function __construct(
        public string $portName,
        public \DateTimeInterface $departureAt,
    ) {
    }
}
