<?php

namespace App\Tests\Repository;

use App\Enum\NotificationResultEnum;
use App\Repository\NotificationRunRepository;
use Doctrine\DBAL\Connection;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

class NotificationRunRepositoryTest extends KernelTestCase
{
    /** 実運用の日付と重ならない、テスト専用の日付 */
    private const BASE_DATE = '2020-01-01';

    private NotificationRunRepository $repository;
    private Connection $conn;

    protected function setUp(): void
    {
        self::bootKernel();
        $this->repository = static::getContainer()->get(NotificationRunRepository::class);
        $this->conn       = static::getContainer()->get(EntityManagerInterface::class)->getConnection();
        $this->cleanup();
    }

    protected function tearDown(): void
    {
        $this->cleanup();
        parent::tearDown();
    }

    private function cleanup(): void
    {
        $this->conn->executeStatement('DELETE FROM notification_runs WHERE run_date < ?', ['2021-01-01']);
    }

    private function date(string $modifier = '+0 days'): \DateTimeImmutable
    {
        return (new \DateTimeImmutable(self::BASE_DATE))->modify($modifier);
    }

    private function resultOf(\DateTimeImmutable $date, int $slot): ?string
    {
        $value = $this->conn->fetchOne(
            'SELECT result FROM notification_runs WHERE run_date = ? AND slot = ?',
            [$date->format('Y-m-d'), $slot],
        );

        return $value === false ? null : (string) $value;
    }

    public function testClaimSucceedsOnlyOncePerDateAndSlot(): void
    {
        $date = $this->date();

        $this->assertTrue($this->repository->claim($date, 6));
        $this->assertFalse($this->repository->claim($date, 6));
        $this->assertTrue($this->repository->claim($date, 15));
        $this->assertTrue($this->repository->claim($date->modify('+1 day'), 6));
        $this->assertSame('pending', $this->resultOf($date, 6));
    }

    public function testFinishUpdatesOnlyPendingRows(): void
    {
        $date = $this->date();
        $this->repository->claim($date, 6);

        $this->repository->finish($date, 6, NotificationResultEnum::Sent, 3, null);
        $this->assertSame('sent', $this->resultOf($date, 6));
        $this->assertSame(
            3,
            (int) $this->conn->fetchOne('SELECT item_count FROM notification_runs WHERE run_date = ? AND slot = 6', [$date->format('Y-m-d')]),
        );

        $this->repository->finish($date, 6, NotificationResultEnum::Failed, 0, 'boom');
        $this->assertSame('sent', $this->resultOf($date, 6), '結果が決まった回は書き換えない');
    }

    public function testDeleteOlderThanKeepsBoundaryDate(): void
    {
        $boundary = $this->date('+100 days');
        $this->repository->claim($boundary->modify('-1 day'), 6);
        $this->repository->claim($boundary, 6);

        $deleted = $this->repository->deleteOlderThan($boundary);

        $this->assertSame(1, $deleted);
        $this->assertNull($this->resultOf($boundary->modify('-1 day'), 6));
        $this->assertSame('pending', $this->resultOf($boundary, 6));
    }
}
