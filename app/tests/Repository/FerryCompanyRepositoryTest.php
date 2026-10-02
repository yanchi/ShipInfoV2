<?php

namespace App\Tests\Repository;

use App\Entity\FerryCompany;
use App\Entity\Route;
use App\Enum\RouteDirectionEnum;
use App\Repository\FerryCompanyRepository;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

class FerryCompanyRepositoryTest extends KernelTestCase
{
    private FerryCompanyRepository $repository;
    private EntityManagerInterface $em;
    /** @var int[] */
    private array $companyIds = [];

    protected function setUp(): void
    {
        self::bootKernel();
        $this->repository = static::getContainer()->get(FerryCompanyRepository::class);
        $this->em         = static::getContainer()->get(EntityManagerInterface::class);
    }

    protected function tearDown(): void
    {
        $conn = $this->em->getConnection();
        foreach ($this->companyIds as $id) {
            $conn->executeStatement('DELETE FROM routes WHERE ferry_company_id = ?', [$id]);
            $conn->executeStatement('DELETE FROM ferry_companies WHERE id = ?', [$id]);
        }
        parent::tearDown();
    }

    /** 有効で、direction のある有効な航路を持つ会社だけ。航路が2本あっても1回だけ */
    public function testFindBoardCompanies(): void
    {
        $board         = $this->company('対象', true, [[true, RouteDirectionEnum::Down], [true, RouteDirectionEnum::Up]]);
        $inactive      = $this->company('無効な会社', false, [[true, RouteDirectionEnum::Down]]);
        $inactiveRoute = $this->company('無効な航路だけ', true, [[false, RouteDirectionEnum::Down]]);
        $noDirection   = $this->company('方向なし', true, [[true, null]]);
        $noRoutes      = $this->company('航路なし', true, []);
        $this->em->clear();

        $ids = array_map(static fn (FerryCompany $c) => $c->getId(), $this->repository->findBoardCompanies());

        $this->assertCount(1, array_keys($ids, $board, true));
        foreach ([$inactive, $inactiveRoute, $noDirection, $noRoutes] as $id) {
            $this->assertNotContains($id, $ids);
        }
        $sorted = $ids;
        sort($sorted);
        $this->assertSame($sorted, $ids);
    }

    /** @param list<array{0: bool, 1: ?RouteDirectionEnum}> $routes */
    private function company(string $label, bool $active, array $routes): int
    {
        $company = (new FerryCompany())->setName("会社一覧テスト（{$label}）")->setActive($active);
        $this->em->persist($company);
        foreach ($routes as $i => [$routeActive, $direction]) {
            $this->em->persist((new Route())
                ->setFerryCompany($company)
                ->setName("会社一覧テスト航路{$i}")
                ->setDirection($direction)
                ->setActive($routeActive));
        }
        $this->em->flush();
        $this->companyIds[] = $company->getId();

        return $company->getId();
    }
}
