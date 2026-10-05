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
     * 有効な航路を1本も持たない会社も結果に含める（`routes` が空配列になる）。
     * トップページ側で「航路情報がありません。」を表示し、設定漏れを黙って隠さないため。
     * 航路の絞り込みは WHERE ではなく JOIN の WITH 句で行う必要がある
     * （WHERE に置くと LEFT JOIN で NULL になった行が除外され INNER JOIN と同じ挙動になる）。
     *
     * @return array<int, array{company: FerryCompany, routes: array<int, array{route: \App\Entity\Route, status: OperationStatus|null}>}>
     */
    public function findTodayByAllCompanies(): array
    {
        $today = new \DateTimeImmutable('today');

        $qb = $this->getEntityManager()->createQueryBuilder();
        $qb->select('fc', 'r')
            ->from(FerryCompany::class, 'fc')
            ->leftJoin('fc.routes', 'r', 'WITH', 'r.active = :active')
            ->where('fc.active = :active')
            ->setParameter('active', true)
            ->orderBy('fc.id', 'ASC')
            ->addOrderBy('r.id', 'ASC');

        /** @var FerryCompany[] $ferryCompanies */
        $ferryCompanies = $qb->getQuery()->getResult();

        $result   = [];
        $routeIds = [];

        foreach ($ferryCompanies as $company) {
            // DB から読んだエンティティなので ID は必ずある
            $companyId          = (int) $company->getId();
            $result[$companyId] = [
                'company' => $company,
                'routes'  => [],
            ];
            foreach ($company->getRoutes() as $route) {
                if ($route->isActive()) {
                    $routeId                                = (int) $route->getId();
                    $result[$companyId]['routes'][$routeId] = [
                        'route'  => $route,
                        'status' => null,
                    ];
                    $routeIds[] = $routeId;
                }
            }
        }

        if (empty($routeIds)) {
            return $result;
        }

        $conn         = $this->getEntityManager()->getConnection();
        $placeholders = implode(',', array_fill(0, count($routeIds), '?'));
        $sql          = "
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
            $ids      = array_map(static fn (array $row): int => (int) $row['id'], $rows);
            $statuses = $this->findBy(['id' => $ids]);

            foreach ($statuses as $status) {
                $routeId   = (int) $status->getRoute()->getId();
                $companyId = (int) $status->getRoute()->getFerryCompany()->getId();
                if (isset($result[$companyId]['routes'][$routeId])) {
                    $result[$companyId]['routes'][$routeId]['status'] = $status;
                }
            }
        }

        return $result;
    }

    /**
     * 会社別ページ用: $today〜$days-1 日先の、その会社の有効な航路の運航状況（航路・日付ごとに最新の1件）。
     * 情報がある日・航路だけを返す。$today は呼び出し側から受け取る（ボードと同じ日付にそろえるため）。
     *
     * @return array<string, list<OperationStatus>> [Y-m-d => 航路 ID 順]
     */
    public function findUpcomingByCompany(FerryCompany $company, \DateTimeImmutable $today, int $days): array
    {
        $today = $today->setTime(0, 0);
        $to    = $today->modify(sprintf('+%d days', $days - 1));

        $sql = '
            SELECT os.id
            FROM operation_statuses os
            INNER JOIN routes r ON r.id = os.route_id
            INNER JOIN (
                SELECT route_id, valid_date, MAX(scraped_at) AS latest_scraped_at
                FROM operation_statuses
                WHERE valid_date BETWEEN :from AND :to
                  AND route_id IN (SELECT id FROM routes WHERE ferry_company_id = :company)
                GROUP BY route_id, valid_date
            ) latest ON os.route_id   = latest.route_id
                    AND os.valid_date  = latest.valid_date
                    AND os.scraped_at  = latest.latest_scraped_at
            WHERE os.valid_date BETWEEN :from AND :to
              AND r.ferry_company_id = :company
              AND r.active = 1
        ';
        $ids = $this->getEntityManager()->getConnection()->executeQuery($sql, [
            'from'    => $today->format('Y-m-d'),
            'to'      => $to->format('Y-m-d'),
            'company' => $company->getId(),
        ])->fetchFirstColumn();

        if ($ids === []) {
            return [];
        }

        /** @var list<OperationStatus> $statuses */
        $statuses = $this->createQueryBuilder('os')
            ->select('os', 'r')
            ->join('os.route', 'r')
            ->where('os.id IN (:ids)')
            ->setParameter('ids', $ids)
            ->orderBy('os.validDate', 'ASC')
            ->addOrderBy('r.id', 'ASC')
            ->getQuery()
            ->getResult();

        $result = [];
        foreach ($statuses as $status) {
            $result[$status->getValidDate()->format('Y-m-d')][] = $status;
        }

        return $result;
    }

    /**
     * 通知用: $from から $days 日分の、有効な会社・有効な航路の運航状況（航路・日付ごとに最新の1件。全状態）。
     * 港だけ通常以外の便にも航路×日付の状態を添えるため、状態では絞らない（対象かどうかは呼び出し側が見る）。
     * 並びは日付 → 航路 ID。
     *
     * @return list<OperationStatus>
     */
    public function findLatestBetween(\DateTimeImmutable $from, int $days): array
    {
        $from = $from->setTime(0, 0);
        $to   = $from->modify(sprintf('+%d days', $days - 1));

        $sql = '
            SELECT os.id
            FROM operation_statuses os
            INNER JOIN routes r ON r.id = os.route_id
            INNER JOIN ferry_companies fc ON fc.id = r.ferry_company_id
            INNER JOIN (
                SELECT route_id, valid_date, MAX(scraped_at) AS latest_scraped_at
                FROM operation_statuses
                WHERE valid_date BETWEEN :from AND :to
                GROUP BY route_id, valid_date
            ) latest ON os.route_id   = latest.route_id
                    AND os.valid_date  = latest.valid_date
                    AND os.scraped_at  = latest.latest_scraped_at
            WHERE os.valid_date BETWEEN :from AND :to
              AND r.active = 1
              AND fc.active = 1
        ';
        $ids = $this->getEntityManager()->getConnection()->executeQuery($sql, [
            'from' => $from->format('Y-m-d'),
            'to'   => $to->format('Y-m-d'),
        ])->fetchFirstColumn();

        if ($ids === []) {
            return [];
        }

        /** @var list<OperationStatus> $statuses */
        $statuses = $this->createQueryBuilder('os')
            ->select('os', 'r', 'fc')
            ->join('os.route', 'r')
            ->join('r.ferryCompany', 'fc')
            ->where('os.id IN (:ids)')
            ->setParameter('ids', $ids)
            ->orderBy('os.validDate', 'ASC')
            ->addOrderBy('r.id', 'ASC')
            ->getQuery()
            ->getResult();

        return $statuses;
    }
}
