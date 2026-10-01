<?php

namespace App\Tests\Repository;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Enum\OperationStatusEnum;
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

    /** 今日〜3日先だけ。昨日・4日先・無効な航路・他社は入らない。航路・日付ごとに最新の1件 */
    public function testFindUpcomingByCompany(): void
    {
        $em      = static::getContainer()->get('doctrine')->getManager();
        $company    = (new FerryCompany())->setName('会社別リポジトリテスト会社')->setActive(true);
        $other      = (new FerryCompany())->setName('会社別リポジトリテスト他社')->setActive(true);
        $active     = (new Route())->setFerryCompany($company)->setName('有効航路')->setActive(true);
        $inactive   = (new Route())->setFerryCompany($company)->setName('無効航路')->setActive(false);
        $otherRoute = (new Route())->setFerryCompany($other)->setName('他社航路')->setActive(true);
        foreach ([$company, $other, $active, $inactive, $otherRoute] as $entity) {
            $em->persist($entity);
        }

        $today = new \DateTimeImmutable('today');
        $make  = static fn (Route $route, int $offset, OperationStatusEnum $status, string $scrapedAt = '-1 hour') => (new OperationStatus())
            ->setRoute($route)
            ->setStatus($status)
            ->setValidDate(\DateTime::createFromImmutable($today->modify("{$offset} days")))
            ->setScrapedAt(new \DateTime($scrapedAt))
            ->setSourceUrl('https://example.invalid/test');
        foreach ([-1, 0, 3, 4] as $offset) {
            $em->persist($make($active, $offset, OperationStatusEnum::Operating));
        }
        // 今日の分は後から取った欠航が最新
        $em->persist($make($active, 0, OperationStatusEnum::Cancelled, 'now'));
        $em->persist($make($inactive, 1, OperationStatusEnum::Operating));
        $em->persist($make($otherRoute, 1, OperationStatusEnum::Operating));
        $em->flush();

        try {
            $result = $this->repository->findUpcomingByCompany($company, 4);

            $this->assertSame([$today->format('Y-m-d'), $today->modify('+3 days')->format('Y-m-d')], array_keys($result));
            $this->assertCount(1, $result[$today->format('Y-m-d')]);
            $this->assertSame(OperationStatusEnum::Cancelled, $result[$today->format('Y-m-d')][0]->getStatus());
            $this->assertSame('有効航路', $result[$today->modify('+3 days')->format('Y-m-d')][0]->getRoute()->getName());
        } finally {
            $conn = $em->getConnection();
            foreach ([$company->getId(), $other->getId()] as $id) {
                $conn->executeStatement('DELETE os FROM operation_statuses os JOIN routes r ON r.id = os.route_id WHERE r.ferry_company_id = ?', [$id]);
                $conn->executeStatement('DELETE FROM routes WHERE ferry_company_id = ?', [$id]);
                $conn->executeStatement('DELETE FROM ferry_companies WHERE id = ?', [$id]);
            }
        }
    }
}
