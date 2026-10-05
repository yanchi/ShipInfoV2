<?php

namespace App\Enum;

enum NotificationResultEnum: string
{
    /** 回を確保した。結果はまだ無い（送信の途中で落ちたらこのまま残り、再送しない） */
    case Pending       = 'pending';
    case Sent          = 'sent';
    case None          = 'none';
    case NotConfigured = 'not_configured';
    case Failed        = 'failed';
}
