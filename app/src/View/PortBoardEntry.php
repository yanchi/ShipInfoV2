<?php

namespace App\View;

use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;

/**
 * 出発港の行に出す1便ぶん（または「便なし」「情報なし」）。
 */
final readonly class PortBoardEntry
{
    public function __construct(
        public DepartureDisplayStateEnum $state,
        public ?OperationStatusEnum $status = null,
        public ?string $companyName = null,
        public ?string $shipName = null,
        public ?\DateTimeInterface $departureAt = null,
        public ?\DateTimeInterface $arrivalAt = null,
        public ?string $detail = null,
        public ?\DateTimeInterface $checkedAt = null,
    ) {
    }

    /**
     * 到着予定の表示（例：「19:00着」「翌19:00着」）。到着日が出港日（無ければ $day）の2日以上後なら日付つき。
     */
    public function arrivalText(\DateTimeInterface $day): ?string
    {
        if ($this->arrivalAt === null) {
            return null;
        }

        $base    = \DateTimeImmutable::createFromInterface($this->departureAt ?? $day)->setTime(0, 0);
        $arrival = \DateTimeImmutable::createFromInterface($this->arrivalAt);
        $diff    = (int) $base->diff($arrival->setTime(0, 0))->format('%r%a');

        return match (true) {
            $diff === 0 => $arrival->format('H:i') . '着',
            $diff === 1 => '翌' . $arrival->format('H:i') . '着',
            default     => $arrival->format('n/j H:i') . '着',
        };
    }
}
