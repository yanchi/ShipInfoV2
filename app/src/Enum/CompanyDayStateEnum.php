<?php

namespace App\Enum;

/**
 * 会社別ページの日付ごとの状態（表示専用。DB には持たない）。
 *
 * - Services:  その会社の便がある
 * - NoService: 便が無いと確認できた（その会社の no_service の行がある）
 * - NoInfo:    その会社の行が1つも無い（まだ取得していない・取得に失敗した）
 */
enum CompanyDayStateEnum: string
{
    case Services  = 'services';
    case NoService = 'no_service';
    case NoInfo    = 'no_info';
}
