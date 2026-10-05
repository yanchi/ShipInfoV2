<?php

namespace App\Entity;

use App\Enum\NotificationResultEnum;
use App\Repository\NotificationRunRepository;
use Doctrine\ORM\Mapping as ORM;

/**
 * 通知の確認回（日付 × 時刻枠）。同じ回を二重に送らないための記録（specs/8-schedule-change-mail/data-model.md）。
 * 書き込みは NotificationRunRepository（DBAL）が行う。ここはスキーマと読み取り用。
 */
#[ORM\Entity(repositoryClass: NotificationRunRepository::class)]
#[ORM\Table(name: 'notification_runs')]
#[ORM\UniqueConstraint(name: 'uniq_notification_run', columns: ['run_date', 'slot'])]
#[ORM\HasLifecycleCallbacks]
class NotificationRun
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\Column(type: 'date_immutable')]
    private ?\DateTimeImmutable $runDate = null;

    #[ORM\Column(type: 'smallint', options: ['unsigned' => true])]
    private int $slot = 0;

    #[ORM\Column(length: 32, enumType: NotificationResultEnum::class)]
    private NotificationResultEnum $result = NotificationResultEnum::Pending;

    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    private int $itemCount = 0;

    #[ORM\Column(type: 'text', nullable: true)]
    private ?string $errorMessage = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $createdAt = null;

    #[ORM\Column(type: 'datetime')]
    private ?\DateTimeInterface $updatedAt = null;

    #[ORM\PrePersist]
    public function onPrePersist(): void
    {
        $now             = new \DateTime();
        $this->createdAt = $now;
        $this->updatedAt = $now;
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

    public function getRunDate(): ?\DateTimeImmutable
    {
        return $this->runDate;
    }

    public function setRunDate(\DateTimeImmutable $runDate): static
    {
        $this->runDate = $runDate;

        return $this;
    }

    public function getSlot(): int
    {
        return $this->slot;
    }

    public function setSlot(int $slot): static
    {
        $this->slot = $slot;

        return $this;
    }

    public function getResult(): NotificationResultEnum
    {
        return $this->result;
    }

    public function setResult(NotificationResultEnum $result): static
    {
        $this->result = $result;

        return $this;
    }

    public function getItemCount(): int
    {
        return $this->itemCount;
    }

    public function setItemCount(int $itemCount): static
    {
        $this->itemCount = $itemCount;

        return $this;
    }

    public function getErrorMessage(): ?string
    {
        return $this->errorMessage;
    }

    public function setErrorMessage(?string $errorMessage): static
    {
        $this->errorMessage = $errorMessage;

        return $this;
    }

    public function getCreatedAt(): ?\DateTimeInterface
    {
        return $this->createdAt;
    }

    public function getUpdatedAt(): ?\DateTimeInterface
    {
        return $this->updatedAt;
    }
}
