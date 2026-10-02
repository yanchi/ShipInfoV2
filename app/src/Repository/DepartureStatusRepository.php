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
     * 寄港順（RouteStopRepository::findBoardStops）と同じく、有効な会社の、有効で direction のある航路だけを対象にする。
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
            ->andWhere('r.active = :active')
            ->andWhere('fc.active = :active')
            ->andWhere('r.direction IS NOT NULL')
            ->setParameter('active', true)
            ->setParameter('from', $from->format('Y-m-d'))
            ->setParameter('to', $to->format('Y-m-d'))
            ->orderBy('d.departureDate', 'ASC')
            ->addOrderBy('d.scheduledDepartureAt', 'ASC')
            ->addOrderBy('fc.id', 'ASC')
            ->getQuery()
            ->getResult();
    }

    /**
     * 会社ごとの最終確認時刻（MAX(checked_at)）。$today の前日以降の行だけを見る（idx_departure_date_port が効く）。
     * 有効な会社の、有効で direction のある航路だけを対象にする。行が1つも無い会社はキーが無い（呼び出し側で古い扱いにする）。
     *
     * @return array<int, \DateTimeImmutable> [companyId => 最終確認時刻]
     */
    public function findLatestCheckedAtByCompany(\DateTimeImmutable $today): array
    {
        $rows = $this->createQueryBuilder('d')
            ->select('IDENTITY(r.ferryCompany) AS companyId', 'MAX(d.checkedAt) AS checkedAt')
            ->join('d.route', 'r')
            ->join('r.ferryCompany', 'fc')
            ->where('d.departureDate >= :from')
            ->andWhere('r.active = :active')
            ->andWhere('fc.active = :active')
            ->andWhere('r.direction IS NOT NULL')
            ->setParameter('from', $today->modify('-1 day')->format('Y-m-d'))
            ->setParameter('active', true)
            ->groupBy('r.ferryCompany')
            ->getQuery()
            ->getArrayResult();

        $result = [];
        foreach ($rows as $row) {
            if ($row['checkedAt'] !== null) {
                $result[(int) $row['companyId']] = new \DateTimeImmutable($row['checkedAt']);
            }
        }

        return $result;
    }
}
