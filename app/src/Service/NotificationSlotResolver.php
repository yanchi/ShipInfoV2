<?php

namespace App\Service;

/**
 * 通知の確認回（日本時間の 1・6・15 時）を決める。
 */
class NotificationSlotResolver
{
    /** 確認時刻（時） */
    public const SLOTS = [1, 6, 15];

    /** 確認時刻からこの分数より前なら、その回の起動とみなす（起動の遅れの吸収。遅れて送らない） */
    public const WINDOW_MINUTES = 10;

    /**
     * 確認時刻から WINDOW_MINUTES 分未満ならその回。それ以外は null。
     */
    public function resolve(\DateTimeImmutable $now): ?int
    {
        foreach (self::SLOTS as $slot) {
            $elapsed = $now->getTimestamp() - $now->setTime($slot, 0, 0)->getTimestamp();
            if ($elapsed >= 0 && $elapsed < self::WINDOW_MINUTES * 60) {
                return $slot;
            }
        }

        return null;
    }

    /**
     * `--slot` の値を回に直す。
     *
     * @throws \InvalidArgumentException 1・6・15 以外
     */
    public function fromOption(string $value): int
    {
        if (!ctype_digit($value) || !in_array((int) $value, self::SLOTS, true)) {
            throw new \InvalidArgumentException(sprintf('--slot は %s のどれかを指定してください。', implode('・', self::SLOTS)));
        }

        return (int) $value;
    }
}
