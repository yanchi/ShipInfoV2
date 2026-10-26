<?php

namespace App\View;

/**
 * トップの会社カードに出す臨時便の1行（「◆ 臨時便 鹿児島 16:00発」）の港と出港時刻。
 * $skipsPorts は、今日その方向の臨時便の行のどれかが「この港を出たあとに抜港あり」か（「・抜港あり」を出すか。16-extra-skip-flag）。
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
