<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * 会社ページに出す船の名前 ship_names と会社の別名 aliases（どちらも JSON の文字列の配列、NULL 可）を ferry_companies に足す。
 * スクレイパーは読み書きしないので、スクレイパーのモデルは変えない。NULL 可なのは、スクレイパーのテストが
 * この 2 列を知らずに行を入れても落ちないようにするため（specs/19-search-query-wording/research.md R2）。
 * 船が入れ替わったら、新しいマイグレーションで値を直す。
 */
final class Version20261124000000 extends AbstractMigration
{
    /** scraper_class => [ship_names, aliases]。値は specs/19-search-query-wording/data-model.md */
    private const COMPANIES = [
        'MarueFerry' => [['フェリー波之上', 'フェリーあけぼの'], ['Aライン（エーライン）']],
        'MarixLine'  => [['クイーンコーラルクロス', 'クイーンコーラルプラス'], null],
    ];

    public function getDescription(): string
    {
        return 'ferry_companies に ship_names・aliases を足す';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE ferry_companies ADD ship_names JSON DEFAULT NULL, ADD aliases JSON DEFAULT NULL');
        // 配列でない JSON（文字列など）が入ると、FerryCompany を読むとき（ヘッダーで全ページ）に型エラーになる。DB で止める
        $this->addSql("ALTER TABLE ferry_companies ADD CONSTRAINT chk_ferry_companies_ship_names CHECK (ship_names IS NULL OR JSON_TYPE(ship_names) = 'ARRAY')");
        $this->addSql("ALTER TABLE ferry_companies ADD CONSTRAINT chk_ferry_companies_aliases CHECK (aliases IS NULL OR JSON_TYPE(aliases) = 'ARRAY')");
        foreach (self::COMPANIES as $scraperClass => [$shipNames, $aliases]) {
            $this->addSql(
                'UPDATE ferry_companies SET ship_names = ?, aliases = ? WHERE scraper_class = ?',
                [self::json($shipNames), self::json($aliases), $scraperClass],
            );
        }
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE ferry_companies DROP CHECK chk_ferry_companies_ship_names, DROP CHECK chk_ferry_companies_aliases');
        $this->addSql('ALTER TABLE ferry_companies DROP ship_names, DROP aliases');
    }

    /** @param list<string>|null $values */
    private static function json(?array $values): ?string
    {
        return $values === null ? null : json_encode($values, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    }
}
