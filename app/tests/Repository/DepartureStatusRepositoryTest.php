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
        $this->em         = static::getContainer()->get(EntityManagerInterface::class);
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

    /** 会社ごとの最大値。前日より前の行は見ない。無効な会社・航路、direction の無い航路は入らない。行が無い会社はキーが無い */
    public function testFindLatestCheckedAtByCompany(): void
    {
        $port  = $this->em->getRepository(Port::class)->findOneBy(['name' => '名瀬']);
        $today = new \DateTimeImmutable('today');

        $make = function (string $label, bool $companyActive, array $routes) use ($port): FerryCompany {
            $company = (new FerryCompany())->setName("最終確認テスト会社（{$label}）")->setActive($companyActive);
            $this->em->persist($company);
            foreach ($routes as [$routeActive, $direction, $rows]) {
                $route = (new Route())
                    ->setFerryCompany($company)
                    ->setName("最終確認テスト航路（{$label}）")
                    ->setDirection($direction)
                    ->setActive($routeActive);
                $this->em->persist($route);
                foreach ($rows as $i => [$dateOffset, $checkedAt]) {
                    $this->em->persist((new DepartureStatus())
                        ->setRoute($route)
                        ->setPort($port)
                        ->setDepartureDate(\DateTime::createFromImmutable((new \DateTimeImmutable('today'))->modify("{$dateOffset} days")))
                        ->setShipName("船{$i}")
                        ->setStatus(OperationStatusEnum::Operating)
                        ->setContentHash(str_repeat('a', 64))
                        ->setCheckedAt(new \DateTime($checkedAt)));
                }
            }
            $this->em->flush();
            $this->extraCompanyIds[] = $company->getId();

            return $company;
        };

        $main = $make('対象', true, [
            [true, RouteDirectionEnum::Down, [[0, 'today 06:00'], [1, 'today 07:30'], [-1, 'yesterday 20:00'], [-2, 'today 09:00']]],
            [false, RouteDirectionEnum::Up, [[0, 'today 10:00']]],
            [true, null, [[0, 'today 11:00']]],
        ]);
        $inactive = $make('無効', false, [[true, RouteDirectionEnum::Down, [[0, 'today 08:00']]]]);
        $old      = $make('古い行だけ', true, [[true, RouteDirectionEnum::Down, [[-2, 'today 08:00']]]]);
        $this->em->clear();

        $result = $this->repository->findLatestCheckedAtByCompany($today);

        $this->assertSame($today->setTime(7, 30)->format('Y-m-d H:i:s'), $result[(int) $main->getId()]->format('Y-m-d H:i:s'));
        $this->assertArrayNotHasKey($inactive->getId(), $result);
        $this->assertArrayNotHasKey($old->getId(), $result);
    }

    /** 通常運航以外の状態だけ。運航予定（null）・通常運航・便なし、範囲外、無効な会社・航路、direction の無い航路は返らない */
    public function testFindIrregularBetween(): void
    {
        $port  = $this->em->getRepository(Port::class)->findOneBy(['name' => '名瀬']);
        $today = new \DateTimeImmutable('today');

        $main     = (new FerryCompany())->setName('通知テスト会社')->setActive(true);
        $inactive = (new FerryCompany())->setName('通知テスト無効会社')->setActive(false);
        $make     = fn (FerryCompany $c, string $name, ?RouteDirectionEnum $d, bool $active = true) => (new Route())
            ->setFerryCompany($c)->setName($name)->setDirection($d)->setActive($active);
        $route         = $make($main, '通知テスト航路', RouteDirectionEnum::Down);
        $inactiveRoute = $make($main, '通知テスト無効航路', RouteDirectionEnum::Down, false);
        $noDirection   = $make($main, '通知テスト方向なし', null);
        $otherRoute    = $make($inactive, '通知テスト無効会社の航路', RouteDirectionEnum::Down);
        foreach ([$main, $inactive, $route, $inactiveRoute, $noDirection, $otherRoute] as $entity) {
            $this->em->persist($entity);
        }

        $row = fn (Route $r, int $offset, string $ship, ?OperationStatusEnum $status) => (new DepartureStatus())
            ->setRoute($r)
            ->setPort($port)
            ->setDepartureDate(\DateTime::createFromImmutable($today->modify("{$offset} days")))
            ->setShipName($ship)
            ->setStatus($status)
            ->setContentHash(str_repeat('a', 64));
        foreach ([
            $row($route, 0, 'cancelled', OperationStatusEnum::Cancelled),
            $row($route, 1, 'delayed', OperationStatusEnum::Delayed),
            $row($route, 2, 'suspended', OperationStatusEnum::Suspended),
            $row($route, 3, 'unknown', OperationStatusEnum::Unknown),
            $row($route, 0, 'operating', OperationStatusEnum::Operating),
            $row($route, 0, 'no_service', OperationStatusEnum::NoService),
            $row($route, 0, 'null', null),
            $row($route, -1, 'yesterday', OperationStatusEnum::Cancelled),
            $row($route, 4, 'day4', OperationStatusEnum::Cancelled),
            $row($inactiveRoute, 0, 'inactive-route', OperationStatusEnum::Cancelled),
            $row($noDirection, 0, 'no-direction', OperationStatusEnum::Cancelled),
            $row($otherRoute, 0, 'inactive-company', OperationStatusEnum::Cancelled),
        ] as $status) {
            $this->em->persist($status);
        }
        $this->em->flush();
        $this->companyId       = $main->getId();
        $this->extraCompanyIds = [$inactive->getId()];
        $this->em->clear();

        $ships = array_map(
            static fn (DepartureStatus $d) => $d->getShipName(),
            $this->repository->findIrregularBetween($today, 4),
        );
        $ships = array_values(array_intersect($ships, ['cancelled', 'delayed', 'suspended', 'unknown', 'operating', 'no_service', 'null', 'yesterday', 'day4', 'inactive-route', 'no-direction', 'inactive-company']));

        $this->assertSame(['cancelled', 'delayed', 'suspended', 'unknown'], $ships);
    }
}
