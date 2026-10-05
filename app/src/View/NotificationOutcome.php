<?php

namespace App\View;

use App\Enum\NotificationResultEnum;

/**
 * メール送信の結果。
 */
final readonly class NotificationOutcome
{
    /**
     * @param list<string> $missingSettings 足りない設定の名前（MAILER_DSN・NOTIFY_FROM・NOTIFY_TO）
     */
    public function __construct(
        public NotificationResultEnum $result,
        public ?string $errorSummary = null,
        public array $missingSettings = [],
    ) {
    }
}
