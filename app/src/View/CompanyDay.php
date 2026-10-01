<?php

namespace App\View;

use App\Entity\OperationStatus;
use App\Enum\CompanyDayStateEnum;

/**
 * 会社別ページの1日分。
 */
final readonly class CompanyDay
{
    /**
     * @param list<OperationStatus> $routeSummaries 航路単位の要約行（情報がある航路だけ。航路 ID 順）
     */
    public function __construct(
        public \DateTimeImmutable $date,
        public CompanyDayStateEnum $state,
        public array $routeSummaries,
        /** その会社の便の行。state が Services のときだけ入る */
        public ?PortBoardDay $board = null,
    ) {
    }
}
