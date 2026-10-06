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
        public ?int $companyId = null,
    ) {
    }

    /** 便がある（発表済み・運航予定）。情報なし・便なしは便として数えない */
    public function isDeparture(): bool
    {
        return \in_array($this->state, [DepartureDisplayStateEnum::Status, DepartureDisplayStateEnum::Scheduled], true);
    }

    /** 欠航・条件付・遅延・運休（異常の要約に入れ、行を目立たせる） */
    public function isAlert(): bool
    {
        return $this->state === DepartureDisplayStateEnum::Status
            && \in_array($this->status, [OperationStatusEnum::Cancelled, OperationStatusEnum::Delayed, OperationStatusEnum::Skipped, OperationStatusEnum::Suspended], true);
    }

    /** 出港時刻を過ぎた通常運航・運航予定の便（異常の便は薄くしない） */
    public function isDeparted(\DateTimeInterface $now): bool
    {
        if ($this->isAlert() || $this->departureAt === null) {
            return false;
        }

        return $this->departureAt < $now
            && ($this->state === DepartureDisplayStateEnum::Scheduled || $this->status === OperationStatusEnum::Operating);
    }

    /** 行に確認時刻を出すか（方向の見出しの時刻と分単位で比べる） */
    public function checkedAtDiffersFrom(?\DateTimeInterface $common): bool
    {
        if ($this->checkedAt === null) {
            return false;
        }
        if ($common === null) {
            return true;
        }

        return $this->checkedAt->format('Y-m-d H:i') !== $common->format('Y-m-d H:i');
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
