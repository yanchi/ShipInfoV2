<?php

namespace App\Repository;

use App\Entity\DepartureStatus;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<DepartureStatus>
 */
class DepartureStatusRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, DepartureStatus::class);
    }

    /**
     * 港別ページ用: $from から $days 日分の港別ステータスを、航路（会社込み）・港・運航会社と一緒に1本のクエリで取る。
     *
     * @return list<DepartureStatus>
     */
    public function findForBoard(\DateTimeImmutable $from, int $days): array
    {
        $to = $from->modify(sprintf('+%d days', $days - 1));

        return $this->createQueryBuilder('d')
            ->select('d', 'r', 'fc', 'p', 'ob')
            ->join('d.route', 'r')
            ->join('r.ferryCompany', 'fc')
            ->join('d.port', 'p')
            ->leftJoin('d.operatedByCompany', 'ob')
            ->where('d.departureDate BETWEEN :from AND :to')
            ->andWhere('r.direction IS NOT NULL')
            ->setParameter('from', $from->format('Y-m-d'))
            ->setParameter('to', $to->format('Y-m-d'))
            ->orderBy('d.departureDate', 'ASC')
            ->addOrderBy('d.scheduledDepartureAt', 'ASC')
            ->addOrderBy('fc.id', 'ASC')
            ->getQuery()
            ->getResult();
    }
}
