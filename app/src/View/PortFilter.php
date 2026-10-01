<?php

namespace App\View;

use App\Entity\Port;
use App\Enum\RouteDirectionEnum;

/**
 * 港別ページの絞り込み条件（出発港・方向）。null はそれぞれ「全港」「両方向」。
 */
final readonly class PortFilter
{
    public function __construct(
        public ?int $portId = null,
        public ?RouteDirectionEnum $direction = null,
        /** Cookie に保存した条件があるか（「保存を解除」を出すかの判定） */
        public bool $hasSaved = false,
    ) {
    }

    public static function none(): self
    {
        return new self();
    }

    public function isActive(): bool
    {
        return $this->portId !== null || $this->direction !== null;
    }

    public function matches(RouteDirectionEnum $direction, Port $port): bool
    {
        return ($this->direction === null || $this->direction === $direction)
            && ($this->portId === null || $this->portId === $port->getId());
    }

    /**
     * 「和泊発・下り」のような絞り込み中の表示。絞り込んでいなければ null。
     *
     * @param list<Port> $ports 港 ID から港名を引くための一覧
     */
    public function label(array $ports): ?string
    {
        $parts = [];
        foreach ($ports as $port) {
            if ($port->getId() === $this->portId) {
                $parts[] = $port->getName() . '発';
                break;
            }
        }
        if ($this->direction !== null) {
            $parts[] = $this->direction === RouteDirectionEnum::Down ? '下り' : '上り';
        }

        return $parts !== [] ? implode('・', $parts) : null;
    }

    /**
     * URL・Cookie 用。null のキーは出さない。
     *
     * @return array{port?: int, dir?: string}
     */
    public function toQuery(): array
    {
        $query = [];
        if ($this->portId !== null) {
            $query['port'] = $this->portId;
        }
        if ($this->direction !== null) {
            $query['dir'] = $this->direction->value;
        }

        return $query;
    }
}
