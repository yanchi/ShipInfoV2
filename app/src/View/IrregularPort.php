<?php

namespace App\View;

use App\Enum\OperationStatusEnum;

/**
 * 通知メールに載せる、通常運航以外の港（出発港ごと）。
 */
final readonly class IrregularPort
{
    public function __construct(
        public string $portName,
        public ?string $shipName,
        public ?\DateTimeInterface $departureAt,
        public OperationStatusEnum $status,
        public ?string $detail,
    ) {
    }
}
