<?php

namespace App\Enum;

enum OperationStatusEnum: string
{
    case Operating = 'operating';
    case Cancelled = 'cancelled';
    case Delayed   = 'delayed';
    case Skipped   = 'skipped';
    case Suspended = 'suspended';
    case Unknown   = 'unknown';
    case NoService = 'no_service';

    /** サイトのバッジと通知メールで共通の文言 */
    public function label(): string
    {
        return match ($this) {
            self::Operating => '通常運航',
            self::Delayed   => '条件付・遅延',
            self::Skipped   => '抜港',
            self::Cancelled => '欠航',
            self::Suspended => '運休',
            self::Unknown   => '不明',
            self::NoService => '便なし',
        };
    }

    /** 通常運航以外として知らせる状態か（運航なし・便なしは対象外） */
    public function isIrregular(): bool
    {
        return match ($this) {
            self::Delayed, self::Skipped, self::Cancelled, self::Suspended, self::Unknown => true,
            self::Operating, self::NoService                                              => false,
        };
    }

    /**
     * @return list<self>
     */
    public static function irregularCases(): array
    {
        return array_values(array_filter(self::cases(), static fn (self $case): bool => $case->isIrregular()));
    }
}
