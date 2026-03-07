<?php

namespace App\Entity;

use App\Enum\OperationStatusEnum;
use App\Repository\OperationStatusRepository;
use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity(repositoryClass: OperationStatusRepository::class)]
#[ORM\Table(name: 'operation_statuses')]
#[ORM\Index(columns: ['route_id', 'valid_date'], name: 'idx_route_date')]
#[ORM\Index(columns: ['valid_date', 'status'], name: 'idx_date_status')]
class OperationStatus
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'bigint', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: Route::class, inversedBy: 'operationStatuses')]
    #[ORM\JoinColumn(nullable: false)]
    private ?Route $route = null;

    #[ORM\Column(type: 'string', enumType: OperationStatusEnum::class)]
    private OperationStatusEnum $status = OperationStatusEnum::Unknown;

    #[ORM\Column(type: 'text', nullable: true)]
    private ?string $statusDetail = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    private ?\DateTimeInterface $departureTime = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    private ?\DateTimeInterface $arrivalTime = null;

    #[ORM\Column(type: 'date')]
    private ?\DateTimeInterface $validDate = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $scrapedAt = null;

    #[ORM\Column(length: 512, nullable: true)]
    private ?string $sourceUrl = null;

    #[ORM\Column(length: 64, nullable: true)]
    private ?string $rawHtmlHash = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $createdAt = null;

    #[ORM\PrePersist]
    public function onPrePersist(): void
    {
        $this->createdAt = new \DateTime();
        if ($this->scrapedAt === null) {
            $this->scrapedAt = new \DateTime();
        }
    }

    public function getId(): ?int { return $this->id; }
    public function getRoute(): ?Route { return $this->route; }
    public function setRoute(?Route $route): static { $this->route = $route; return $this; }
    public function getStatus(): OperationStatusEnum { return $this->status; }
    public function setStatus(OperationStatusEnum $status): static { $this->status = $status; return $this; }
    public function getStatusDetail(): ?string { return $this->statusDetail; }
    public function setStatusDetail(?string $statusDetail): static { $this->statusDetail = $statusDetail; return $this; }
    public function getDepartureTime(): ?\DateTimeInterface { return $this->departureTime; }
    public function setDepartureTime(?\DateTimeInterface $departureTime): static { $this->departureTime = $departureTime; return $this; }
    public function getArrivalTime(): ?\DateTimeInterface { return $this->arrivalTime; }
    public function setArrivalTime(?\DateTimeInterface $arrivalTime): static { $this->arrivalTime = $arrivalTime; return $this; }
    public function getValidDate(): ?\DateTimeInterface { return $this->validDate; }
    public function setValidDate(\DateTimeInterface $validDate): static { $this->validDate = $validDate; return $this; }
    public function getScrapedAt(): ?\DateTimeInterface { return $this->scrapedAt; }
    public function setScrapedAt(\DateTimeInterface $scrapedAt): static { $this->scrapedAt = $scrapedAt; return $this; }
    public function getSourceUrl(): ?string { return $this->sourceUrl; }
    public function setSourceUrl(?string $sourceUrl): static { $this->sourceUrl = $sourceUrl; return $this; }
    public function getRawHtmlHash(): ?string { return $this->rawHtmlHash; }
    public function setRawHtmlHash(?string $rawHtmlHash): static { $this->rawHtmlHash = $rawHtmlHash; return $this; }
    public function getCreatedAt(): ?\DateTimeInterface { return $this->createdAt; }
}
