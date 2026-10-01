<?php

namespace App\Repository;

use App\Entity\FerryCompany;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<FerryCompany>
 */
class FerryCompanyRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, FerryCompany::class);
    }

    /**
     * 港別ページに便が出る会社（有効で、direction のある有効な航路を持つ会社）。情報の古さの判定の基準。ID 順。
     *
     * @return list<FerryCompany>
     */
    public function findBoardCompanies(): array
    {
        return $this->createQueryBuilder('fc')
            ->where('fc.active = :active')
            ->andWhere('EXISTS (SELECT r.id FROM App\Entity\Route r WHERE r.ferryCompany = fc AND r.active = :active AND r.direction IS NOT NULL)')
            ->setParameter('active', true)
            ->orderBy('fc.id', 'ASC')
            ->getQuery()
            ->getResult();
    }

    /**
     * 有効な会社（共通ヘッダーの「各社」）。ID 順。
     *
     * @return list<FerryCompany>
     */
    public function findActive(): array
    {
        return $this->findBy(['active' => true], ['id' => 'ASC']);
    }
}
