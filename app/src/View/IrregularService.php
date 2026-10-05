<?php

namespace App\View;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Enum\OperationStatusEnum;

/**
 * 通知メールの1件。(航路, 日付) ごとに、航路×日付の状態と通常運航以外の港をまとめたもの。
 */
final readonly class IrregularService
{
    /**
     * @param list<IrregularPort> $ports 出港予定時刻順（時刻なしは最後）
     */
    public function __construct(
        public FerryCompany $company,
        public Route $route,
        public \DateTimeImmutable $date,
        public ?OperationStatus $routeStatus,
        public array $ports,
    ) {
    }

    /** 航路×日付の状態が通常運航以外か */
    public function isRouteIrregular(): bool
    {
        return $this->routeStatus !== null && $this->routeStatus->getStatus()->isIrregular();
    }

    public function directionLabel(): string
    {
        return $this->route->getDirection()?->label() ?? $this->route->getName();
    }

    public function statusText(): string
    {
        if ($this->routeStatus !== null && $this->isRouteIrregular()) {
            return $this->routeStatus->getStatus()->label();
        }

        if ($this->routeStatus?->getStatus() === OperationStatusEnum::Operating) {
            return OperationStatusEnum::Operating->label() . '（途中の港に変更あり）';
        }

        return '情報なし（途中の港に変更あり）';
    }

    /** 航路×日付が通常運航以外のときの備考 */
    public function detail(): ?string
    {
        if (!$this->isRouteIrregular()) {
            return null;
        }

        $detail = trim((string) $this->routeStatus?->getStatusDetail());

        return $detail === '' ? null : $detail;
    }
}
