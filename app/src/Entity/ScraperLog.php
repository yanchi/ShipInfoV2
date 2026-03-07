<?php

namespace App\Entity;

use App\Enum\ScraperStatusEnum;
use App\Repository\ScraperLogRepository;
use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity(repositoryClass: ScraperLogRepository::class)]
#[ORM\Table(name: 'scraper_logs')]
class ScraperLog
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'bigint', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: FerryCompany::class)]
    #[ORM\JoinColumn(nullable: false)]
    private ?FerryCompany $ferryCompany = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $startedAt = null;

    #[ORM\Column(type: 'datetime', nullable: true)]
    private ?\DateTimeInterface $finishedAt = null;

    #[ORM\Column(type: 'string', enumType: ScraperStatusEnum::class)]
    private ScraperStatusEnum $status = ScraperStatusEnum::Running;

    #[ORM\Column(type: 'integer')]
    private int $recordsCreated = 0;

    #[ORM\Column(type: 'integer')]
    private int $recordsUpdated = 0;

    #[ORM\Column(type: 'text', nullable: true)]
    private ?string $errorMessage = null;

    #[ORM\PrePersist]
    public function onPrePersist(): void
    {
        if ($this->startedAt === null) {
            $this->startedAt = new \DateTime();
        }
    }

    public function getId(): ?int { return $this->id; }
    public function getFerryCompany(): ?FerryCompany { return $this->ferryCompany; }
    public function setFerryCompany(?FerryCompany $ferryCompany): static { $this->ferryCompany = $ferryCompany; return $this; }
    public function getStartedAt(): ?\DateTimeInterface { return $this->startedAt; }
    public function setStartedAt(\DateTimeInterface $startedAt): static { $this->startedAt = $startedAt; return $this; }
    public function getFinishedAt(): ?\DateTimeInterface { return $this->finishedAt; }
    public function setFinishedAt(?\DateTimeInterface $finishedAt): static { $this->finishedAt = $finishedAt; return $this; }
    public function getStatus(): ScraperStatusEnum { return $this->status; }
    public function setStatus(ScraperStatusEnum $status): static { $this->status = $status; return $this; }
    public function getRecordsCreated(): int { return $this->recordsCreated; }
    public function setRecordsCreated(int $recordsCreated): static { $this->recordsCreated = $recordsCreated; return $this; }
    public function getRecordsUpdated(): int { return $this->recordsUpdated; }
    public function setRecordsUpdated(int $recordsUpdated): static { $this->recordsUpdated = $recordsUpdated; return $this; }
    public function getErrorMessage(): ?string { return $this->errorMessage; }
    public function setErrorMessage(?string $errorMessage): static { $this->errorMessage = $errorMessage; return $this; }
}
