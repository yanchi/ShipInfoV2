<?php

namespace App\View;

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
}
