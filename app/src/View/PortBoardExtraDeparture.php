<?php

namespace App\View;

/**
 * トップの会社カードに出す臨時便の1行（「◆ 臨時便 鹿児島 16:00発」）の港と出港時刻。
 * $skipsPorts は、今日を出る臨時便の運航に抜港があるか（「・抜港あり」を出すか。15-extra-voyage-badge）。
 */
final readonly class PortBoardExtraDeparture
{
    public function __construct(
        public string $portName,
        public \DateTimeInterface $departureAt,
        public bool $skipsPorts = false,
    ) {
    }
}
