<?php

namespace App\View;

use App\Entity\Port;
use App\Enum\RouteDirectionEnum;

/**
 * 異常の要約の1項目（欠航・条件付・遅延・運休の便）。
 */
final readonly class PortAlert
{
    public function __construct(
        public \DateTimeImmutable $date,
        public RouteDirectionEnum $direction,
        public Port $port,
        public string $arrivalPortName,
        public PortBoardEntry $entry,
    ) {
    }

    /** 一覧の行の id と同じ形（r-{Y-m-d}-{direction}-{portId}） */
    public function anchor(): string
    {
        return sprintf('r-%s-%s-%d', $this->date->format('Y-m-d'), $this->direction->value, $this->port->getId());
    }
}
