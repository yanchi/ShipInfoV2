<?php

namespace App\Entity;

use App\Repository\FerryCompanyRepository;
use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\Common\Collections\Collection;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Validator\Constraints as Assert;

#[ORM\Entity(repositoryClass: FerryCompanyRepository::class)]
#[ORM\Table(name: 'ferry_companies')]
#[ORM\HasLifecycleCallbacks]
class FerryCompany
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\Column(length: 255)]
    #[Assert\NotBlank]
    private string $name = '';

    #[ORM\Column(length: 512, nullable: true)]
    private ?string $websiteUrl = null;

    #[ORM\Column(length: 255, nullable: true)]
    private ?string $scraperClass = null;

    #[ORM\Column(type: 'boolean')]
    private bool $active = true;

    /**
     * 運航している船の名前（表示の順）。NULL は「無し」（specs/19-search-query-wording/data-model.md）
     *
     * @var list<string>|null
     */
    #[ORM\Column(type: 'json', nullable: true)]
    private ?array $shipNames = null;

    /**
     * 検索で使われる会社の別の呼び方（表示用の文字列。例: 「Aライン（エーライン）」）。NULL は「無し」
     *
     * @var list<string>|null
     */
    #[ORM\Column(type: 'json', nullable: true)]
    private ?array $aliases = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $createdAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $updatedAt = null;

    /** @var Collection<int, Route> */
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

    public function getId(): ?int
    {
        return $this->id;
    }

    public function getName(): string
    {
        return $this->name;
    }

    public function setName(string $name): static
    {
        $this->name = $name;

        return $this;
    }

    public function getWebsiteUrl(): ?string
    {
        return $this->websiteUrl;
    }

    public function setWebsiteUrl(?string $websiteUrl): static
    {
        $this->websiteUrl = $websiteUrl;

        return $this;
    }

    public function getScraperClass(): ?string
    {
        return $this->scraperClass;
    }

    public function setScraperClass(?string $scraperClass): static
    {
        $this->scraperClass = $scraperClass;

        return $this;
    }

    public function isActive(): bool
    {
        return $this->active;
    }

    public function setActive(bool $active): static
    {
        $this->active = $active;

        return $this;
    }

    /** @return list<string> 前後の空白を除き、空の要素は捨てる */
    public function getShipNames(): array
    {
        return self::clean($this->shipNames);
    }

    /** @param list<string> $shipNames 掃除して空になれば NULL で持つ */
    public function setShipNames(array $shipNames): static
    {
        $this->shipNames = self::clean($shipNames) ?: null;

        return $this;
    }

    /** @return list<string> 前後の空白を除き、空の要素は捨てる */
    public function getAliases(): array
    {
        return self::clean($this->aliases);
    }

    /** @param list<string> $aliases 掃除して空になれば NULL で持つ */
    public function setAliases(array $aliases): static
    {
        $this->aliases = self::clean($aliases) ?: null;

        return $this;
    }

    /**
     * マイグレーションや手の SQL で入った値も読むので、文字列以外の要素（null・数値・配列）も捨てる
     *
     * @param array<mixed>|null $values
     *
     * @return list<string>
     */
    private static function clean(?array $values): array
    {
        $strings = array_map(trim(...), array_filter($values ?? [], is_string(...)));

        return array_values(array_filter($strings, static fn (string $v): bool => $v !== ''));
    }

    public function getCreatedAt(): ?\DateTimeInterface
    {
        return $this->createdAt;
    }

    public function getUpdatedAt(): ?\DateTimeInterface
    {
        return $this->updatedAt;
    }

    /** @return Collection<int, Route> */
    public function getRoutes(): Collection
    {
        return $this->routes;
    }
}
