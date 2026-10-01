<?php

namespace App\Tests\Repository;

use App\Entity\DepartureStatus;
use App\Entity\FerryCompany;
use App\Entity\Port;
use App\Entity\Route;
use App\Entity\RouteStop;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Repository\DepartureStatusRepository;
use App\Repository\RouteStopRepository;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

class DepartureStatusRepositoryTest extends KernelTestCase
{
    private DepartureStatusRepository $repository;
    private EntityManagerInterface $em;
    private ?int $companyId = null;
    /** @var int[] */
    private array $extraCompanyIds = [];

    protected function setUp(): void
    {
        self::bootKernel();
        $this->repository = static::getContainer()->get(DepartureStatusRepository::class);
        $this->em         = static::getContainer()->get('doctrine')->getManager();
    }

    protected function tearDown(): void
    {
        $conn = $this->em->getConnection();
        foreach (array_filter([$this->companyId, ...$this->extraCompanyIds]) as $id) {
            $conn->executeStatement(
                'DELETE d FROM departure_statuses d JOIN routes r ON r.id = d.route_id WHERE r.ferry_company_id = ?',
                [$id]
            );
            $conn->executeStatement(
                'DELETE s FROM route_stops s JOIN routes r ON r.id = s.route_id WHERE r.ferry_company_id = ?',
                [$id]
            );
            $conn->executeStatement('DELETE FROM routes WHERE ferry_company_id = ?', [$id]);
            $conn->executeStatement('DELETE FROM ferry_companies WHERE id = ?', [$id]);
        }
        parent::tearDown();
    }

    public function testFindForBoardReturnsOnlyRowsInRangeWithRelations(): void
    {
        $port = $this->em->getRepository(Port::class)->findOneBy(['name' => '名瀬']);
        $this->assertNotNull($port, 'ports の初期データがありません（マイグレーションを確認）');

        $company = (new FerryCompany())->setName('港別リポジトリテスト会社')->setActive(true);
        $route   = (new Route())
            ->setFerryCompany($company)
            ->setName('港別リポジトリテスト航路')
            ->setDirection(RouteDirectionEnum::Down)
            ->setActive(true);
        $this->em->persist($company);
        $this->em->persist($route);

        $today = new \DateTimeImmutable('today');
        foreach ([-1, 0, 3, 4] as $offset) {
            $this->em->persist((new DepartureStatus())
                ->setRoute($route)
                ->setPort($port)
                ->setDepartureDate(\DateTime::createFromImmutable($today->modify("{$offset} days")))
                ->setShipName("船{$offset}")
                ->setStatus(OperationStatusEnum::Operating)
                ->setOperatedByCompany($company)
                ->setContentHash(str_repeat('a', 64)));
        }
        $this->em->flush();
        $this->companyId = $company->getId();
        $this->em->clear();

        $rows = array_values(array_filter(
            $this->repository->findForBoard($today, 4),
            fn (DepartureStatus $d) => $d->getRoute()->getFerryCompany()->getId() === $this->companyId,
        ));

        $this->assertSame(['船0', '船3'], array_map(static fn (DepartureStatus $d) => $d->getShipName(), $rows));
        $first = $rows[0];
        $this->assertSame('名瀬', $first->getPort()->getName());
        $this->assertSame('港別リポジトリテスト会社', $first->getRoute()->getFerryCompany()->getName());
        $this->assertSame('港別リポジトリテスト会社', $first->getOperatedByCompany()->getName());
        $this->assertSame(RouteDirectionEnum::Down, $first->getRoute()->getDirection());
    }

    public function testFindForBoardExcludesInactiveRoutes(): void
    {
        $port = $this->em->getRepository(Port::class)->findOneBy(['name' => '名瀬']);
        $this->assertNotNull($port, 'ports の初期データがありません（マイグレーションを確認）');

        $company = (new FerryCompany())->setName('港別リポジトリテスト会社')->setActive(true);
        $this->em->persist($company);
        $today = new \DateTimeImmutable('today');
        foreach (['有効' => true, '無効' => false] as $label => $active) {
            $route = (new Route())
                ->setFerryCompany($company)
                ->setName("港別リポジトリテスト航路（{$label}）")
                ->setDirection(RouteDirectionEnum::Down)
                ->setActive($active);
            $this->em->persist($route);
            $this->em->persist((new DepartureStatus())
                ->setRoute($route)
                ->setPort($port)
                ->setDepartureDate(\DateTime::createFromImmutable($today))
                ->setShipName("{$label}の船")
                ->setStatus(OperationStatusEnum::Operating)
                ->setContentHash(str_repeat('a', 64)));
        }
        $this->em->flush();
        $this->companyId = $company->getId();
        $this->em->clear();

        $ships = array_map(
            static fn (DepartureStatus $d) => $d->getShipName(),
            array_values(array_filter(
                $this->repository->findForBoard($today, 4),
                fn (DepartureStatus $d) => $d->getRoute()->getFerryCompany()->getId() === $this->companyId,
            )),
        );

        $this->assertSame(['有効の船'], $ships);
    }

    public function testFindForBoardExcludesInactiveCompanies(): void
    {
        $port  = $this->em->getRepository(Port::class)->findOneBy(['name' => '名瀬']);
        $today = new \DateTimeImmutable('today');

        foreach (['有効' => true, '無効' => false] as $label => $active) {
            $company = (new FerryCompany())->setName("港別リポジトリテスト会社（{$label}）")->setActive($active);
            $route   = (new Route())
                ->setFerryCompany($company)
                ->setName("港別リポジトリテスト航路（{$label}）")
                ->setDirection(RouteDirectionEnum::Down)
                ->setActive(true);
            $this->em->persist($company);
            $this->em->persist($route);
            $this->em->persist((new DepartureStatus())
                ->setRoute($route)
                ->setPort($port)
                ->setDepartureDate(\DateTime::createFromImmutable($today))
                ->setShipName("{$label}の会社の船")
                ->setStatus(OperationStatusEnum::Operating)
                ->setContentHash(str_repeat('a', 64)));
            $this->em->flush();
            $this->extraCompanyIds[] = $company->getId();
        }
        $this->em->clear();

        $ships = array_map(
            static fn (DepartureStatus $d) => $d->getShipName(),
            array_values(array_filter(
                $this->repository->findForBoard($today, 4),
                fn (DepartureStatus $d) => in_array($d->getRoute()->getFerryCompany()->getId(), $this->extraCompanyIds, true),
            )),
        );

        $this->assertSame(['有効の会社の船'], $ships);
    }

    public function testFindBoardStopsExcludesInactiveCompanies(): void
    {
        $ports = [];
        foreach (['鹿児島', '亀徳', '那覇'] as $name) {
            $ports[] = $this->em->getRepository(Port::class)->findOneBy(['name' => $name]);
        }

        // 無効な会社だけが「鹿児島 → 亀徳 → 那覇」という寄港順を持つ
        $company = (new FerryCompany())->setName('港別リポジトリテスト会社（無効）')->setActive(false);
        $route   = (new Route())
            ->setFerryCompany($company)
            ->setName('港別リポジトリテスト航路（無効な会社）')
            ->setDirection(RouteDirectionEnum::Down)
            ->setActive(true);
        $this->em->persist($company);
        $this->em->persist($route);
        foreach ($ports as $i => $port) {
            $this->em->persist((new RouteStop())->setRoute($route)->setPort($port)->setStopOrder($i + 1));
        }
        $this->em->flush();
        $this->extraCompanyIds[] = $company->getId();
        $this->em->clear();

        $stops = static::getContainer()->get(RouteStopRepository::class)->findBoardStops();

        $orders = array_map(
            static fn (array $d) => array_map(static fn (Port $p) => $p->getName(), $d['departurePorts']),
            $stops,
        );
        $this->assertNotContains(['鹿児島', '亀徳'], $orders, '無効な会社の寄港順が使われています。');
    }
}
