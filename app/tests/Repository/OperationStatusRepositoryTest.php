<?php

namespace App\Tests\Repository;

use App\Entity\FerryCompany;
use App\Entity\Route;
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

    /**
     * 有効な航路を1本も持たない会社もトップページ用の結果に含まれること。
     * INNER JOIN のままだと会社ごと結果から消え、「航路情報がありません。」に到達しない。
     */
    public function testFindTodayByAllCompaniesIncludesCompanyWithoutRoutes(): void
    {
        $em      = static::getContainer()->get('doctrine')->getManager();
        $company = (new FerryCompany())
            ->setName('航路未設定テスト会社')
            ->setActive(true);

        $em->persist($company);
        $em->flush();
        $companyId = $company->getId();

        try {
            $result = $this->repository->findTodayByAllCompanies();

            $this->assertArrayHasKey($companyId, $result, '航路0件の会社が結果に含まれていません。');
            $this->assertSame([], $result[$companyId]['routes']);
        } finally {
            $em->remove($company);
            $em->flush();
        }
    }

    /**
     * 無効な航路しか持たない会社も結果に含まれ、無効航路は除外されること。
     */
    public function testFindTodayByAllCompaniesExcludesInactiveRoutesButKeepsCompany(): void
    {
        $em      = static::getContainer()->get('doctrine')->getManager();
        $company = (new FerryCompany())
            ->setName('無効航路のみテスト会社')
            ->setActive(true);
        $route = (new Route())
            ->setFerryCompany($company)
            ->setName('無効航路')
            ->setActive(false);

        $em->persist($company);
        $em->persist($route);
        $em->flush();
        $companyId = $company->getId();

        try {
            $result = $this->repository->findTodayByAllCompanies();

            $this->assertArrayHasKey($companyId, $result);
            $this->assertSame([], $result[$companyId]['routes'], '無効な航路が結果に含まれています。');
        } finally {
            $em->remove($route);
            $em->remove($company);
            $em->flush();
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
