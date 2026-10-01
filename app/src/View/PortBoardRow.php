<?php

namespace App\View;

use App\Entity\Port;

final readonly class PortBoardRow
{
    /**
     * @param list<PortBoardEntry> $entries 1件以上（2社とも便があれば2件）
     */
    public function __construct(
        public Port $port,
        public array $entries,
    ) {
    }
}
