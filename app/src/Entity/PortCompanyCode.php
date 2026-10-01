<?php

namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

/**
 * 会社ごとの港の外部コード（マルエーの便検索の港コードなど）。
 */
#[ORM\Entity]
#[ORM\Table(name: 'port_company_codes')]
#[ORM\UniqueConstraint(name: 'uniq_port_company', columns: ['port_id', 'ferry_company_id'])]
class PortCompanyCode
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column(type: 'integer', options: ['unsigned' => true])]
    private ?int $id = null;

    #[ORM\ManyToOne(targetEntity: Port::class)]
    #[ORM\JoinColumn(nullable: false)]
    private ?Port $port = null;

    #[ORM\ManyToOne(targetEntity: FerryCompany::class)]
    #[ORM\JoinColumn(nullable: false)]
    private ?FerryCompany $ferryCompany = null;

    #[ORM\Column(length: 32)]
    private string $externalCode = '';

    public function getId(): ?int { return $this->id; }
    public function getPort(): ?Port { return $this->port; }
    public function setPort(?Port $port): static { $this->port = $port; return $this; }
    public function getFerryCompany(): ?FerryCompany { return $this->ferryCompany; }
    public function setFerryCompany(?FerryCompany $ferryCompany): static { $this->ferryCompany = $ferryCompany; return $this; }
    public function getExternalCode(): string { return $this->externalCode; }
    public function setExternalCode(string $externalCode): static { $this->externalCode = $externalCode; return $this; }
}
