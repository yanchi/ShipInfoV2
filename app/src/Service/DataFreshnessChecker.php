<?php

namespace App\Service;

use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use Symfony\Contracts\Service\ResetInterface;

/**
 * 表示している情報が古くないかの判定（FR-023、research R10）。
 *
 * 港別ページに便が出る会社ごとの最終確認時刻を見て、STALE_AFTER_HOURS 時間以上前の会社と、
 * 前日以降の行が無い会社を「古い」とする。表示する時刻は、値のある会社の中で一番古い時刻。
 * 結果はリクエストの中で覚えておき、2回目以降はクエリを走らせない（kernel.reset で忘れる）。
 */
class DataFreshnessChecker implements ResetInterface
{
    /** これより前の確認時刻の会社があれば「情報が古い」（警告の文言にもこの値を出す） */
    public const STALE_AFTER_HOURS = 2;

    /** @var array{checkedAt: ?\DateTimeImmutable, isStale: bool, staleCompanies: list<string>, staleHours: int}|null */
    private ?array $result = null;

    public function __construct(
        private readonly DepartureStatusRepository $departureStatusRepository,
        private readonly FerryCompanyRepository $ferryCompanyRepository,
    ) {
    }

    /**
     * @return array{checkedAt: ?\DateTimeImmutable, isStale: bool, staleCompanies: list<string>, staleHours: int}
     */
    public function check(): array
    {
        if ($this->result !== null) {
            return $this->result;
        }

        $now       = new \DateTimeImmutable();
        $threshold = $now->modify(sprintf('-%d hours', self::STALE_AFTER_HOURS));
        $latest    = $this->departureStatusRepository->findLatestCheckedAtByCompany($now->setTime(0, 0));

        $checkedAt = null;
        $stale     = [];
        foreach ($this->ferryCompanyRepository->findBoardCompanies() as $company) {
            $companyCheckedAt = $latest[$company->getId()] ?? null;
            if ($companyCheckedAt === null || $companyCheckedAt <= $threshold) {
                $stale[] = $company->getName();
            }
            if ($companyCheckedAt !== null && ($checkedAt === null || $companyCheckedAt < $checkedAt)) {
                $checkedAt = $companyCheckedAt;
            }
        }

        return $this->result = [
            'checkedAt'      => $checkedAt,
            'isStale'        => $stale !== [],
            'staleCompanies' => $stale,
            'staleHours'     => self::STALE_AFTER_HOURS,
        ];
    }

    public function reset(): void
    {
        $this->result = null;
    }
}
