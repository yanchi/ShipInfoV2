<?php

namespace App\Tests\Service;

use App\Entity\FerryCompany;
use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use App\Service\DataFreshnessChecker;
use PHPUnit\Framework\TestCase;

class DataFreshnessCheckerTest extends TestCase
{
    public function testFreshWhenAllCompaniesAreRecent(): void
    {
        $older = new \DateTimeImmutable('-70 minutes');
        $checker   = $this->checker([1 => new \DateTimeImmutable('-30 minutes'), 2 => $older]);

        $freshness = $checker->check();

        $this->assertFalse($freshness['isStale']);
        $this->assertSame([], $freshness['staleCompanies']);
        // 警告の文言に出す時間数は判定の閾値と同じ
        $this->assertSame(DataFreshnessChecker::STALE_AFTER_HOURS, $freshness['staleHours']);
        // 表示するのは一番古い会社の時刻
        $this->assertEquals($older, $freshness['checkedAt']);
    }

    public function testStaleWhenOneCompanyIsOld(): void
    {
        $checker = $this->checker([1 => new \DateTimeImmutable('-30 minutes'), 2 => new \DateTimeImmutable('-3 hours')]);

        $freshness = $checker->check();

        $this->assertTrue($freshness['isStale']);
        $this->assertSame(['マリックスライン'], $freshness['staleCompanies']);
    }

    /** 前日以降の行が無い会社（スクレイパーが長く止まっている）も古い扱い */
    public function testStaleWhenCompanyHasNoRows(): void
    {
        $recent = new \DateTimeImmutable('-30 minutes');
        $checker    = $this->checker([1 => $recent]);

        $freshness = $checker->check();

        $this->assertTrue($freshness['isStale']);
        $this->assertSame(['マリックスライン'], $freshness['staleCompanies']);
        $this->assertEquals($recent, $freshness['checkedAt']);
    }

    public function testQueriesOnlyOncePerRequest(): void
    {
        $departures = $this->createMock(DepartureStatusRepository::class);
        $departures->expects($this->once())->method('findLatestCheckedAtByCompany')->willReturn([]);
        $companies = $this->createMock(FerryCompanyRepository::class);
        $companies->expects($this->once())->method('findBoardCompanies')->willReturn([]);
        $checker = new DataFreshnessChecker($departures, $companies);

        $checker->check();
        $checker->check();
    }

    public function testResetForgetsResults(): void
    {
        $departures = $this->createMock(DepartureStatusRepository::class);
        $departures->expects($this->exactly(2))->method('findLatestCheckedAtByCompany')->willReturn([]);
        $companies = $this->createMock(FerryCompanyRepository::class);
        $companies->method('findBoardCompanies')->willReturn([]);
        $checker = new DataFreshnessChecker($departures, $companies);

        $checker->check();
        $checker->reset();
        $checker->check();
    }

    /** @param array<int, \DateTimeImmutable> $latest */
    private function checker(array $latest): DataFreshnessChecker
    {
        $departures = $this->createStub(DepartureStatusRepository::class);
        $departures->method('findLatestCheckedAtByCompany')->willReturn($latest);
        $companies = $this->createStub(FerryCompanyRepository::class);
        $companies->method('findBoardCompanies')->willReturn([$this->company(1, 'マルエーフェリー'), $this->company(2, 'マリックスライン')]);

        return new DataFreshnessChecker($departures, $companies);
    }

    private function company(int $id, string $name): FerryCompany
    {
        $company = (new FerryCompany())->setName($name);
        (new \ReflectionProperty($company, 'id'))->setValue($company, $id);

        return $company;
    }
}
