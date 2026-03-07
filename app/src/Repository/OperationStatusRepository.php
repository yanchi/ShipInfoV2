<?php

namespace App\Repository;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<OperationStatus>
 */
class OperationStatusRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, OperationStatus::class);
    }

    /**
     * トップページ用: 本日の全社・全航路の最新ステータスを返す。
     *
     * @return array<int, array{company: \App\Entity\FerryCompany, routes: array<int, array{route: \App\Entity\Route, status: OperationStatus|null}>}>
     */
    public function findTodayByAllCompanies(): array
    {
        $today = new \DateTimeImmutable('today');

        $qb = $this->getEntityManager()->createQueryBuilder();
        $qb->select('fc', 'r')
            ->from(\App\Entity\FerryCompany::class, 'fc')
            ->join('fc.routes', 'r')
            ->where('fc.active = :active')
            ->andWhere('r.active = :active')
            ->setParameter('active', true)
            ->orderBy('fc.id', 'ASC')
            ->addOrderBy('r.id', 'ASC');

        /** @var \App\Entity\FerryCompany[] $ferryCompanies */
        $ferryCompanies = $qb->getQuery()->getResult();

        $result   = [];
        $routeIds = [];

        foreach ($ferryCompanies as $company) {
            $result[$company->getId()] = [
                'company' => $company,
                'routes'  => [],
            ];
            foreach ($company->getRoutes() as $route) {
                if ($route->isActive()) {
                    $result[$company->getId()]['routes'][$route->getId()] = [
                        'route'  => $route,
                        'status' => null,
                    ];
                    $routeIds[] = $route->getId();
                }
            }
        }

        if (empty($routeIds)) {
            return $result;
        }

        $conn         = $this->getEntityManager()->getConnection();
        $placeholders = implode(',', array_fill(0, count($routeIds), '?'));
        $sql = "
            SELECT os.*
            FROM operation_statuses os
            INNER JOIN (
                SELECT route_id, MAX(scraped_at) AS latest_scraped_at
                FROM operation_statuses
                WHERE valid_date = ?
                  AND route_id IN ({$placeholders})
                GROUP BY route_id
            ) latest ON os.route_id = latest.route_id
                    AND os.scraped_at = latest.latest_scraped_at
            WHERE os.valid_date = ?
        ";

        $params = array_merge(
            [$today->format('Y-m-d')],
            $routeIds,
            [$today->format('Y-m-d')]
        );

        $rows = $conn->executeQuery($sql, $params)->fetchAllAssociative();

        if (!empty($rows)) {
            $ids      = array_map(static fn(array $row): int => (int) $row['id'], $rows);
            $statuses = $this->findBy(['id' => $ids]);

            foreach ($statuses as $status) {
                $routeId   = $status->getRoute()->getId();
                $companyId = $status->getRoute()->getFerryCompany()->getId();
                if (isset($result[$companyId]['routes'][$routeId])) {
                    $result[$companyId]['routes'][$routeId]['status'] = $status;
                }
            }
        }

        return $result;
    }

    /**
     * 会社別ページ用: 直近 $days 日分の運航状況を日付×航路で返す。
     *
     * @return array<string, array<int, array{route: \App\Entity\Route, status: OperationStatus|null}>>
     */
    public function findRecentByCompany(FerryCompany $company, int $days = 3): array
    {
        $today = new \DateTimeImmutable('today');
        $from  = $today->modify(sprintf('-%d days', $days - 1));

        $routes = [];
        foreach ($company->getRoutes() as $route) {
            if ($route->isActive()) {
                $routes[$route->getId()] = $route;
            }
        }

        if (empty($routes)) {
            return [];
        }

        $result = [];
        for ($i = 0; $i < $days; $i++) {
            $date          = $today->modify("-{$i} days")->format('Y-m-d');
            $result[$date] = [];
            foreach ($routes as $routeId => $route) {
                $result[$date][$routeId] = ['route' => $route, 'status' => null];
            }
        }

        $routeIds     = array_keys($routes);
        $placeholders = implode(',', array_fill(0, count($routeIds), '?'));
        $conn         = $this->getEntityManager()->getConnection();

        $sql = "
            SELECT os.*
            FROM operation_statuses os
            INNER JOIN (
                SELECT route_id, valid_date, MAX(scraped_at) AS latest_scraped_at
                FROM operation_statuses
                WHERE valid_date BETWEEN ? AND ?
                  AND route_id IN ({$placeholders})
                GROUP BY route_id, valid_date
            ) latest ON os.route_id   = latest.route_id
                    AND os.valid_date  = latest.valid_date
                    AND os.scraped_at  = latest.latest_scraped_at
            WHERE os.valid_date BETWEEN ? AND ?
              AND os.route_id IN ({$placeholders})
            ORDER BY os.valid_date DESC
        ";

        $params = array_merge(
            [$from->format('Y-m-d'), $today->format('Y-m-d')],
            $routeIds,
            [$from->format('Y-m-d'), $today->format('Y-m-d')],
            $routeIds
        );

        $rows = $conn->executeQuery($sql, $params)->fetchAllAssociative();

        if (!empty($rows)) {
            $ids      = array_map(static fn(array $row): int => (int) $row['id'], $rows);
            $statuses = $this->findBy(['id' => $ids]);

            foreach ($statuses as $status) {
                $dateKey = $status->getValidDate()->format('Y-m-d');
                $routeId = $status->getRoute()->getId();
                if (isset($result[$dateKey][$routeId])) {
                    $result[$dateKey][$routeId]['status'] = $status;
                }
            }
        }

        return $result;
    }
}
