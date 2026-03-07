<?php

namespace App\Entity;

use ApiPlatform\Metadata\ApiResource;
use ApiPlatform\Metadata\Get;
use ApiPlatform\Metadata\GetCollection;
use App\Repository\FerryCompanyRepository;
use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\Common\Collections\Collection;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Serializer\Annotation\Groups;
use Symfony\Component\Validator\Constraints as Assert;

#[ORM\Entity(repositoryClass: FerryCompanyRepository::class)]
#[ORM\Table(name: 'ferry_companies')]
#[ORM\HasLifecycleCallbacks]
#[ApiResource(
    operations: [
        new GetCollection(),
        new Get(),
    ],
    normalizationContext: ['groups' => ['company:read']],
)]
class FerryCompany
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    #[Groups(['company:read'])]
    private ?int $id = null;

    #[ORM\Column(length: 255)]
    #[Assert\NotBlank]
    #[Groups(['company:read'])]
    private string $name = '';

    #[ORM\Column(length: 512, nullable: true)]
    #[Groups(['company:read'])]
    private ?string $websiteUrl = null;

    #[ORM\Column(length: 255, nullable: true)]
    private ?string $scraperClass = null;

    #[ORM\Column(type: 'boolean')]
    #[Groups(['company:read'])]
    private bool $active = true;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $createdAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $updatedAt = null;

    #[ORM\OneToMany(mappedBy: 'ferryCompany', targetEntity: Route::class)]
    private Collection $routes;

    public function __construct()
    {
        $this->routes = new ArrayCollection();
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
    public function getName(): string { return $this->name; }
    public function setName(string $name): static { $this->name = $name; return $this; }
    public function getWebsiteUrl(): ?string { return $this->websiteUrl; }
    public function setWebsiteUrl(?string $websiteUrl): static { $this->websiteUrl = $websiteUrl; return $this; }
    public function getScraperClass(): ?string { return $this->scraperClass; }
    public function setScraperClass(?string $scraperClass): static { $this->scraperClass = $scraperClass; return $this; }
    public function isActive(): bool { return $this->active; }
    public function setActive(bool $active): static { $this->active = $active; return $this; }
    public function getCreatedAt(): ?\DateTimeInterface { return $this->createdAt; }
    public function getUpdatedAt(): ?\DateTimeInterface { return $this->updatedAt; }

    /** @return Collection<int, Route> */
    public function getRoutes(): Collection { return $this->routes; }
}
