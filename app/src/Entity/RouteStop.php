<?php

namespace App\Entity;

use App\Repository\RouteStopRepository;
use Doctrine\ORM\Mapping as ORM;

/**
 * 航路ごとの寄港順。stop_order = 1 が始発港、最大値が終点（到着港）。
 */
#[ORM\Entity(repositoryClass: RouteStopRepository::class)]
#[ORM\Table(name: 'route_stops')]
#[ORM\UniqueConstraint(name: 'uniq_route_port', columns: ['route_id', 'port_id'])]
#[ORM\UniqueConstraint(name: 'uniq_route_stop_order', columns: ['route_id', 'stop_order'])]
class RouteStop
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: Route::class, inversedBy: 'stops')]
    #[ORM\JoinColumn(nullable: false)]
    private ?Route $route = null;

    #[ORM\ManyToOne(targetEntity: Port::class)]
    #[ORM\JoinColumn(nullable: false)]
    private ?Port $port = null;

    #[ORM\Column(type: 'smallint')]
    private int $stopOrder = 1;

    /** 始発日から何日後にこの港を出るか（予備用） */
    #[ORM\Column(type: 'smallint', options: ['default' => 0])]
    private int $dayOffset = 0;

    public function getId(): ?int { return $this->id; }
    public function getRoute(): ?Route { return $this->route; }
    public function setRoute(?Route $route): static { $this->route = $route; return $this; }
    public function getPort(): ?Port { return $this->port; }
    public function setPort(?Port $port): static { $this->port = $port; return $this; }
    public function getStopOrder(): int { return $this->stopOrder; }
    public function setStopOrder(int $stopOrder): static { $this->stopOrder = $stopOrder; return $this; }
    public function getDayOffset(): int { return $this->dayOffset; }
    public function setDayOffset(int $dayOffset): static { $this->dayOffset = $dayOffset; return $this; }
}
