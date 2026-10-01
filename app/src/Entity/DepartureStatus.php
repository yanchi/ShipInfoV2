<?php

namespace App\Entity;

use App\Enum\OperationStatusEnum;
use App\Repository\DepartureStatusRepository;
use Doctrine\ORM\Mapping as ORM;

/**
 * 会社 × 方向 × 出発港 × 出港日 × 船 の港別ステータス。
 *
 * status が null = 運航予定（未発表）。
 * status が no_service で operatedByCompany がある = この会社は便なし、他社が運航。
 */
#[ORM\Entity(repositoryClass: DepartureStatusRepository::class)]
#[ORM\Table(name: 'departure_statuses')]
#[ORM\UniqueConstraint(name: 'uniq_departure', columns: ['route_id', 'port_id', 'departure_date', 'ship_name'])]
#[ORM\Index(columns: ['departure_date', 'port_id'], name: 'idx_departure_date_port')]
#[ORM\HasLifecycleCallbacks]
class DepartureStatus
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'bigint', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: Route::class)]
    #[ORM\JoinColumn(nullable: false)]
    private ?Route $route = null;

    #[ORM\ManyToOne(targetEntity: Port::class)]
    #[ORM\JoinColumn(nullable: false)]
    private ?Port $port = null;

    #[ORM\Column(type: 'date')]
    private ?\DateTimeInterface $departureDate = null;

    #[ORM\Column(length: 255, options: ['default' => ''])]
    private string $shipName = '';

    #[ORM\Column(length: 32, nullable: true, enumType: OperationStatusEnum::class)]
    private ?OperationStatusEnum $status = null;

    #[ORM\Column(type: 'text', nullable: true)]
    private ?string $statusDetail = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    private ?\DateTimeInterface $scheduledDepartureAt = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    private ?\DateTimeInterface $scheduledArrivalAt = null;

    #[ORM\ManyToOne(targetEntity: FerryCompany::class)]
    #[ORM\JoinColumn(nullable: true)]
    private ?FerryCompany $operatedByCompany = null;

    #[ORM\Column(length: 512, nullable: true)]
    private ?string $sourceUrl = null;

    #[ORM\Column(length: 64, options: ['fixed' => true])]
    private string $contentHash = '';

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $scrapedAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $checkedAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $createdAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $updatedAt = null;

    #[ORM\PrePersist]
    public function onPrePersist(): void
    {
        $now = new \DateTime();
        $this->createdAt = $now;
        $this->updatedAt = $now;
        $this->scrapedAt ??= $now;
        $this->checkedAt ??= $now;
    }

    #[ORM\PreUpdate]
    public function onPreUpdate(): void
    {
        $this->updatedAt = new \DateTime();
    }

    public function getId(): ?int { return $this->id; }
    public function getRoute(): ?Route { return $this->route; }
    public function setRoute(?Route $route): static { $this->route = $route; return $this; }
    public function getPort(): ?Port { return $this->port; }
    public function setPort(?Port $port): static { $this->port = $port; return $this; }
    public function getDepartureDate(): ?\DateTimeInterface { return $this->departureDate; }
    public function setDepartureDate(\DateTimeInterface $departureDate): static { $this->departureDate = $departureDate; return $this; }
    public function getShipName(): string { return $this->shipName; }
    public function setShipName(string $shipName): static { $this->shipName = $shipName; return $this; }
    public function getStatus(): ?OperationStatusEnum { return $this->status; }
    public function setStatus(?OperationStatusEnum $status): static { $this->status = $status; return $this; }
    public function getStatusDetail(): ?string { return $this->statusDetail; }
    public function setStatusDetail(?string $statusDetail): static { $this->statusDetail = $statusDetail; return $this; }
    public function getScheduledDepartureAt(): ?\DateTimeInterface { return $this->scheduledDepartureAt; }
    public function setScheduledDepartureAt(?\DateTimeInterface $at): static { $this->scheduledDepartureAt = $at; return $this; }
    public function getScheduledArrivalAt(): ?\DateTimeInterface { return $this->scheduledArrivalAt; }
    public function setScheduledArrivalAt(?\DateTimeInterface $at): static { $this->scheduledArrivalAt = $at; return $this; }
    public function getOperatedByCompany(): ?FerryCompany { return $this->operatedByCompany; }
    public function setOperatedByCompany(?FerryCompany $company): static { $this->operatedByCompany = $company; return $this; }
    public function getSourceUrl(): ?string { return $this->sourceUrl; }
    public function setSourceUrl(?string $sourceUrl): static { $this->sourceUrl = $sourceUrl; return $this; }
    public function getContentHash(): string { return $this->contentHash; }
    public function setContentHash(string $contentHash): static { $this->contentHash = $contentHash; return $this; }
    public function getScrapedAt(): ?\DateTimeInterface { return $this->scrapedAt; }
    public function setScrapedAt(\DateTimeInterface $scrapedAt): static { $this->scrapedAt = $scrapedAt; return $this; }
    public function getCheckedAt(): ?\DateTimeInterface { return $this->checkedAt; }
    public function setCheckedAt(\DateTimeInterface $checkedAt): static { $this->checkedAt = $checkedAt; return $this; }
    public function getCreatedAt(): ?\DateTimeInterface { return $this->createdAt; }
    public function getUpdatedAt(): ?\DateTimeInterface { return $this->updatedAt; }
}
