<?php

namespace App\Entity;

use ApiPlatform\Metadata\ApiFilter;
use ApiPlatform\Metadata\ApiResource;
use ApiPlatform\Metadata\Get;
use ApiPlatform\Metadata\GetCollection;
use ApiPlatform\Doctrine\Orm\Filter\DateFilter;
use ApiPlatform\Doctrine\Orm\Filter\SearchFilter;
use App\Enum\OperationStatusEnum;
use App\Repository\OperationStatusRepository;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Serializer\Annotation\Groups;

#[ORM\Entity(repositoryClass: OperationStatusRepository::class)]
#[ORM\Table(name: 'operation_statuses')]
#[ORM\Index(columns: ['route_id', 'valid_date'], name: 'idx_route_date')]
#[ORM\Index(columns: ['valid_date', 'status'], name: 'idx_date_status')]
#[ApiResource(
    operations: [
        new GetCollection(),
        new Get(),
    ],
    normalizationContext: ['groups' => ['status:read']],
    order: ['validDate' => 'DESC', 'scrapedAt' => 'DESC'],
)]
#[ApiFilter(SearchFilter::class, properties: ['status' => 'exact', 'route' => 'exact', 'route.ferryCompany' => 'exact'])]
#[ApiFilter(DateFilter::class, properties: ['validDate'])]
class OperationStatus
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'bigint', options: ['unsigned' => true])]
    #[Groups(['status:read'])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: Route::class, inversedBy: 'operationStatuses')]
    #[ORM\JoinColumn(nullable: false)]
    #[Groups(['status:read'])]
    private ?Route $route = null;

    #[ORM\Column(type: 'string', enumType: OperationStatusEnum::class)]
    #[Groups(['status:read'])]
    private OperationStatusEnum $status = OperationStatusEnum::Unknown;

    #[ORM\Column(type: 'text', nullable: true)]
    #[Groups(['status:read'])]
    private ?string $statusDetail = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    #[Groups(['status:read'])]
    private ?\DateTimeInterface $departureTime = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    #[Groups(['status:read'])]
    private ?\DateTimeInterface $arrivalTime = null;

    #[ORM\Column(type: 'date')]
    #[Groups(['status:read'])]
    private ?\DateTimeInterface $validDate = null;

    #[ORM\Column(type: 'datetime')]
    #[Groups(['status:read'])]
    private ?\DateTimeInterface $scrapedAt = null;

    #[ORM\Column(length: 512, nullable: true)]
    #[Groups(['status:read'])]
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
