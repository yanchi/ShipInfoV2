<?php

namespace App\Twig;

use App\Entity\FerryCompany;
use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use Symfony\Contracts\Service\ResetInterface;
use Twig\Extension\AbstractExtension;
use Twig\TwigFunction;

/**
 * 全ページで使う情報（共通ヘッダーの会社一覧、最終確認時刻と古い情報の警告。FR-022・023、research R10・R11）。
 *
 * 結果はリクエストの中で覚えておき、2回目以降はクエリを走らせない（kernel.reset で忘れる）。
 */
class SiteExtension extends AbstractExtension implements ResetInterface
{
    /** これより前の確認時刻の会社があれば「情報が古い」 */
    private const STALE_AFTER = 'PT2H';

    /** @var array{checkedAt: ?\DateTimeImmutable, isStale: bool, staleCompanies: list<string>}|null */
    private ?array $freshness = null;

    /** @var list<FerryCompany>|null */
    private ?array $companies = null;

    public function __construct(
        private readonly DepartureStatusRepository $departureStatusRepository,
        private readonly FerryCompanyRepository $ferryCompanyRepository,
    ) {
    }

    public function getFunctions(): array
    {
        return [
            new TwigFunction('site_freshness', $this->freshness(...)),
            new TwigFunction('site_companies', $this->companies(...)),
        ];
    }

    /**
     * 港別ページに便が出る会社ごとの最終確認時刻を見て、2時間以上前の会社と、前日以降の行が無い会社を「古い」とする。
     * 表示する時刻は、値のある会社の中で一番古い時刻。
     *
     * @return array{checkedAt: ?\DateTimeImmutable, isStale: bool, staleCompanies: list<string>}
     */
    public function freshness(): array
    {
        if ($this->freshness !== null) {
            return $this->freshness;
        }

        $now       = new \DateTimeImmutable();
        $threshold = $now->sub(new \DateInterval(self::STALE_AFTER));
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

        return $this->freshness = ['checkedAt' => $checkedAt, 'isStale' => $stale !== [], 'staleCompanies' => $stale];
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
        $this->freshness = null;
        $this->companies = null;
    }
}
