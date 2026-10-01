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
}
