<?php

namespace App\Entity;

use App\Repository\RouteRepository;
use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\Common\Collections\Collection;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Validator\Constraints as Assert;

#[ORM\Entity(repositoryClass: RouteRepository::class)]
#[ORM\Table(name: 'routes')]
#[ORM\HasLifecycleCallbacks]
class Route
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: FerryCompany::class, inversedBy: 'routes')]
    #[ORM\JoinColumn(nullable: false)]
    private ?FerryCompany $ferryCompany = null;

    #[ORM\Column(length: 255)]
    #[Assert\NotBlank]
    private string $name = '';

    #[ORM\Column(length: 255, nullable: true)]
    private ?string $originPort = null;

    #[ORM\Column(length: 255, nullable: true)]
    private ?string $destinationPort = null;

    #[ORM\Column(type: 'boolean')]
    private bool $active = true;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $createdAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $updatedAt = null;

    #[ORM\OneToMany(mappedBy: 'route', targetEntity: OperationStatus::class)]
    private Collection $operationStatuses;

    public function __construct()
    {
        $this->operationStatuses = new ArrayCollection();
    }

    #[ORM\PrePersist]
    public function onPrePersist(): void
    {
        $this->createdAt = new \DateTime();
        $this->updatedAt = new \DateTime();
    }

    #[ORM\PreUpdate]
    public function onPreUpdate(): void
    {
        $this->updatedAt = new \DateTime();
    }

    public function getId(): ?int { return $this->id; }
    public function getFerryCompany(): ?FerryCompany { return $this->ferryCompany; }
    public function setFerryCompany(?FerryCompany $ferryCompany): static { $this->ferryCompany = $ferryCompany; return $this; }
    public function getName(): string { return $this->name; }
    public function setName(string $name): static { $this->name = $name; return $this; }
    public function getOriginPort(): ?string { return $this->originPort; }
    public function setOriginPort(?string $originPort): static { $this->originPort = $originPort; return $this; }
    public function getDestinationPort(): ?string { return $this->destinationPort; }
    public function setDestinationPort(?string $destinationPort): static { $this->destinationPort = $destinationPort; return $this; }
    public function isActive(): bool { return $this->active; }
    public function setActive(bool $active): static { $this->active = $active; return $this; }
    public function getCreatedAt(): ?\DateTimeInterface { return $this->createdAt; }
    public function getUpdatedAt(): ?\DateTimeInterface { return $this->updatedAt; }

    /** @return Collection<int, OperationStatus> */
    public function getOperationStatuses(): Collection { return $this->operationStatuses; }
}
