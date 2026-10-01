<?php

namespace App\Repository;

use App\Entity\Port;
use App\Entity\RouteStop;
use App\Enum\RouteDirectionEnum;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<RouteStop>
 */
class RouteStopRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, RouteStop::class);
    }

    /**
     * 港別ページ用: 方向ごとの出発港（終点を除く、寄港順）と終点の港。
     *
     * 2社で寄港順が同じ前提なので、方向ごとに最初の航路（route.id 順）の並びを使う。
     * 返す順は下り → 上り。direction が null の航路と無効な航路は対象外。
     *
     * @return list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}>
     */
    public function findBoardStops(): array
    {
        /** @var RouteStop[] $stops */
        $stops = $this->createQueryBuilder('s')
            ->select('s', 'r', 'p')
            ->join('s.route', 'r')
            ->join('s.port', 'p')
            ->where('r.active = :active')
            ->andWhere('r.direction IS NOT NULL')
            ->setParameter('active', true)
            ->orderBy('r.id', 'ASC')
            ->addOrderBy('s.stopOrder', 'ASC')
            ->getQuery()
            ->getResult();

        /** @var array<string, array{routeId: int, ports: list<Port>}> $byDirection */
        $byDirection = [];
        foreach ($stops as $stop) {
            $route     = $stop->getRoute();
            $direction = $route->getDirection()->value;
            $byDirection[$direction] ??= ['routeId' => $route->getId(), 'ports' => []];
            if ($byDirection[$direction]['routeId'] !== $route->getId()) {
                continue;
            }
            $byDirection[$direction]['ports'][] = $stop->getPort();
        }

        $result = [];
        foreach (RouteDirectionEnum::cases() as $direction) {
            $ports = $byDirection[$direction->value]['ports'] ?? [];
            if (count($ports) < 2) {
                continue;
            }
            $arrival  = array_pop($ports);
            $result[] = [
                'direction'      => $direction,
                'departurePorts' => $ports,
                'arrivalPort'    => $arrival,
            ];
        }

        return $result;
    }
}
