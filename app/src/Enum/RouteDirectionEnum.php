<?php

namespace App\Enum;

enum RouteDirectionEnum: string
{
    case Down = 'down';
    case Up   = 'up';

    public function label(): string
    {
        return match ($this) {
            self::Down => '下り（那覇行き）',
            self::Up   => '上り（鹿児島行き）',
        };
    }
}
