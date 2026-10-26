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

        $operating = $this->routeStatus?->getStatus() === OperationStatusEnum::Operating;

        $hasExtra    = false;
        $hasNonExtra = false;
        foreach ($this->ports as $port) {
            if ($port->status === OperationStatusEnum::Extra) {
                $hasExtra = true;
            } else {
                $hasNonExtra = true;
            }
        }

        // 航路が通常運航で臨時便がある日は、通常運航と書かずトップのバッジと同じ「スケジュール変更」にする（15-extra-voyage-badge）。
        // 条件はトップと同じではない：航路×日付が便なし・行なしの日は、途中の港の定期便が分からないので変えない（research R4）
        $head = $operating && $hasExtra ? 'スケジュール変更' : OperationStatusEnum::Operating->label();

        // 臨時便だけの日は、定期便に変更があるとは書かない（臨時便まるごとを「途中の港の変更」と読まれないため）
        if ($hasExtra && !$hasNonExtra) {
            return $operating ? $head . '（臨時便あり）' : '臨時便あり';
        }

        if ($operating) {
            return $head . '（途中の港に変更あり）';
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
