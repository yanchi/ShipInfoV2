<?php

namespace App\Tests\Twig;

use App\Entity\FerryCompany;
use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use App\Twig\SiteExtension;
use PHPUnit\Framework\TestCase;

class SiteExtensionTest extends TestCase
{
    public function testFreshWhenAllCompaniesAreRecent(): void
    {
        $older = new \DateTimeImmutable('-70 minutes');
        $ext   = $this->extension([1 => new \DateTimeImmutable('-30 minutes'), 2 => $older]);

        $freshness = $ext->freshness();

        $this->assertFalse($freshness['isStale']);
        $this->assertSame([], $freshness['staleCompanies']);
        // 表示するのは一番古い会社の時刻
        $this->assertEquals($older, $freshness['checkedAt']);
    }

    public function testStaleWhenOneCompanyIsOld(): void
    {
        $ext = $this->extension([1 => new \DateTimeImmutable('-30 minutes'), 2 => new \DateTimeImmutable('-3 hours')]);

        $freshness = $ext->freshness();

        $this->assertTrue($freshness['isStale']);
        $this->assertSame(['マリックスライン'], $freshness['staleCompanies']);
    }

    /** 前日以降の行が無い会社（スクレイパーが長く止まっている）も古い扱い */
    public function testStaleWhenCompanyHasNoRows(): void
    {
        $recent = new \DateTimeImmutable('-30 minutes');
        $ext    = $this->extension([1 => $recent]);

        $freshness = $ext->freshness();

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
        $companies->expects($this->once())->method('findActive')->willReturn([]);
        $ext = new SiteExtension($departures, $companies);

        $ext->freshness();
        $ext->freshness();
        $ext->companies();
        $ext->companies();
    }

    public function testResetForgetsResults(): void
    {
        $departures = $this->createMock(DepartureStatusRepository::class);
        $departures->expects($this->exactly(2))->method('findLatestCheckedAtByCompany')->willReturn([]);
        $companies = $this->createMock(FerryCompanyRepository::class);
        $companies->method('findBoardCompanies')->willReturn([]);
        $ext = new SiteExtension($departures, $companies);

        $ext->freshness();
        $ext->reset();
        $ext->freshness();
    }

    /** @param array<int, \DateTimeImmutable> $latest */
    private function extension(array $latest): SiteExtension
    {
        $departures = $this->createStub(DepartureStatusRepository::class);
        $departures->method('findLatestCheckedAtByCompany')->willReturn($latest);
        $companies = $this->createStub(FerryCompanyRepository::class);
        $companies->method('findBoardCompanies')->willReturn([$this->company(1, 'マルエーフェリー'), $this->company(2, 'マリックスライン')]);

        return new SiteExtension($departures, $companies);
    }

    private function company(int $id, string $name): FerryCompany
    {
        $company = (new FerryCompany())->setName($name);
        (new \ReflectionProperty($company, 'id'))->setValue($company, $id);

        return $company;
    }
}
