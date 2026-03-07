<?php

namespace App\Tests\Repository;

use App\Entity\FerryCompany;
use App\Repository\OperationStatusRepository;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

class OperationStatusRepositoryTest extends KernelTestCase
{
    private OperationStatusRepository $repository;

    protected function setUp(): void
    {
        self::bootKernel();
        $this->repository = static::getContainer()->get(OperationStatusRepository::class);
    }

    public function testFindTodayByAllCompaniesReturnsArray(): void
    {
        $result = $this->repository->findTodayByAllCompanies();

        $this->assertIsArray($result);

        foreach ($result as $companyId => $data) {
            $this->assertIsInt($companyId);
            $this->assertArrayHasKey('company', $data);
            $this->assertArrayHasKey('routes', $data);
            $this->assertInstanceOf(FerryCompany::class, $data['company']);
            $this->assertIsArray($data['routes']);

            foreach ($data['routes'] as $routeId => $routeData) {
                $this->assertIsInt($routeId);
                $this->assertArrayHasKey('route', $routeData);
                $this->assertArrayHasKey('status', $routeData);
            }
        }
    }

    public function testFindRecentByCompanyReturnsArray(): void
    {
        $companyRepo = static::getContainer()->get(\App\Repository\FerryCompanyRepository::class);
        $companies   = $companyRepo->findAll();

        if (empty($companies)) {
            $this->markTestSkipped('No ferry companies in DB.');
        }

        $company = $companies[0];
        $result  = $this->repository->findRecentByCompany($company, 3);

        $this->assertIsArray($result);

        foreach ($result as $dateKey => $routes) {
            $this->assertMatchesRegularExpression('/^\d{4}-\d{2}-\d{2}$/', $dateKey);
            $this->assertIsArray($routes);

            foreach ($routes as $routeId => $routeData) {
                $this->assertIsInt($routeId);
                $this->assertArrayHasKey('route', $routeData);
                $this->assertArrayHasKey('status', $routeData);
            }
        }
    }

    public function testFindRecentByCompanyReturnsAtMostNDays(): void
    {
        $companyRepo = static::getContainer()->get(\App\Repository\FerryCompanyRepository::class);
        $companies   = $companyRepo->findAll();

        if (empty($companies)) {
            $this->markTestSkipped('No ferry companies in DB.');
        }

        $result = $this->repository->findRecentByCompany($companies[0], 3);

        $this->assertLessThanOrEqual(3, count($result));
    }
}
