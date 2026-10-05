<?php

namespace App\Repository;

use App\Entity\NotificationRun;
use App\Enum\NotificationResultEnum;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\DBAL\Exception\UniqueConstraintViolationException;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<NotificationRun>
 */
class NotificationRunRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, NotificationRun::class);
    }

    /**
     * 通知の回を確保する。すでに確保されていれば false。
     * ORM の flush() で一意キー違反を出すと EntityManager が閉じるので、確保だけは DBAL で行う。
     */
    public function claim(\DateTimeImmutable $runDate, int $slot): bool
    {
        $now = (new \DateTimeImmutable())->format('Y-m-d H:i:s');

        try {
            $this->getEntityManager()->getConnection()->insert('notification_runs', [
                'run_date'   => $runDate->format('Y-m-d'),
                'slot'       => $slot,
                'result'     => NotificationResultEnum::Pending->value,
                'item_count' => 0,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        } catch (UniqueConstraintViolationException) {
            return false;
        }

        return true;
    }

    /**
     * 確保した回に結果を書く。pending の行だけを更新し、結果が決まった回は書き換えない。
     */
    public function finish(
        \DateTimeImmutable $runDate,
        int $slot,
        NotificationResultEnum $result,
        int $itemCount,
        ?string $errorMessage,
    ): void {
        $this->getEntityManager()->getConnection()->executeStatement(
            'UPDATE notification_runs
                SET result = :result, item_count = :count, error_message = :error, updated_at = :now
              WHERE run_date = :date AND slot = :slot AND result = :pending',
            [
                'result'  => $result->value,
                'count'   => $itemCount,
                'error'   => $errorMessage,
                'now'     => (new \DateTimeImmutable())->format('Y-m-d H:i:s'),
                'date'    => $runDate->format('Y-m-d'),
                'slot'    => $slot,
                'pending' => NotificationResultEnum::Pending->value,
            ],
        );
    }

    /**
     * $date より前の回の行を消す。消した行数を返す。
     */
    public function deleteOlderThan(\DateTimeImmutable $date): int
    {
        return (int) $this->getEntityManager()->getConnection()->executeStatement(
            'DELETE FROM notification_runs WHERE run_date < :date',
            ['date' => $date->format('Y-m-d')],
        );
    }
}
