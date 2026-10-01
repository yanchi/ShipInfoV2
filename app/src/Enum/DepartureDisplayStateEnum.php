<?php

namespace App\Enum;

/**
 * 港別ページの1エントリの表示状態（表示専用。DB には持たない）。
 *
 * - Status:    発表済みのステータス（OperationStatusEnum のバッジを出す）
 * - Scheduled: 運航予定（便はあるけどステータス未発表）
 * - NoInfo:    情報なし
 * - NoService: 便なし
 */
enum DepartureDisplayStateEnum: string
{
    case Status    = 'status';
    case Scheduled = 'scheduled';
    case NoInfo    = 'no_info';
    case NoService = 'no_service';
}
