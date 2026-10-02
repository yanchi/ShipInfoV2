<?php

namespace App\Twig;

use App\Entity\FerryCompany;
use App\Repository\FerryCompanyRepository;
use App\Service\DataFreshnessChecker;
use Symfony\Contracts\Service\ResetInterface;
use Twig\Extension\RuntimeExtensionInterface;

/**
 * SiteExtension の関数の中身。会社一覧はリクエストの中で覚えておく（kernel.reset で忘れる）。
 */
class SiteRuntime implements RuntimeExtensionInterface, ResetInterface
{
    /** @var list<FerryCompany>|null */
    private ?array $companies = null;

    public function __construct(
        private readonly DataFreshnessChecker $dataFreshnessChecker,
        private readonly FerryCompanyRepository $ferryCompanyRepository,
    ) {
    }

    /**
     * @return array{checkedAt: ?\DateTimeImmutable, isStale: bool, staleCompanies: list<string>, staleHours: int}
     */
    public function freshness(): array
    {
        return $this->dataFreshnessChecker->check();
    }

    /**
     * @return list<FerryCompany>
     */
    public function companies(): array
    {
        return $this->companies ??= $this->ferryCompanyRepository->findActive();
    }

    public function reset(): void
    {
        $this->companies = null;
    }
}
