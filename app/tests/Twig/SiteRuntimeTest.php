<?php

namespace App\Tests\Twig;

use App\Repository\FerryCompanyRepository;
use App\Service\DataFreshnessChecker;
use App\Twig\SiteRuntime;
use PHPUnit\Framework\TestCase;

class SiteRuntimeTest extends TestCase
{
    public function testCompaniesAreQueriedOncePerRequest(): void
    {
        $companies = $this->createMock(FerryCompanyRepository::class);
        $companies->expects($this->exactly(2))->method('findActive')->willReturn([]);
        $runtime = new SiteRuntime($this->createStub(DataFreshnessChecker::class), $companies);

        $runtime->companies();
        $runtime->companies();
        $runtime->reset();
        $runtime->companies();
    }
}
