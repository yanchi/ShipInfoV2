<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * スクレイパーの SQLAlchemy モデルが書き込む列を足す。
 *
 * - scraper_logs.created_at / updated_at
 * - operation_statuses.updated_at
 *
 * 01_schema.sql とマイグレーションで作った DB にはこの列が無く、スクレイパーが ScraperLog の INSERT で
 * 「Unknown column 'created_at'」になっていた（開発用 DB には手で足した列があり、気づかなかった）。
 *
 * 列がすでにある DB（開発用 DB）では足さず、定義だけほかのテーブルと同じ DATETIME NOT NULL にそろえる。
 * 既存の行は、scraper_logs は started_at / finished_at、operation_statuses は created_at で埋める。
 */
final class Version20261002000000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'scraper_logs.created_at / updated_at と operation_statuses.updated_at を足す';
    }

    public function up(Schema $schema): void
    {
        $scraperLogs       = $schema->getTable('scraper_logs');
        $operationStatuses = $schema->getTable('operation_statuses');

        // NOT NULL の列を既存の行がある表に足すため、いったん DEFAULT を付けて足し、埋めてから DEFAULT を外す
        if (!$scraperLogs->hasColumn('created_at')) {
            $this->addSql('ALTER TABLE scraper_logs ADD created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL');
            $this->addSql('UPDATE scraper_logs SET created_at = started_at');
        }
        if (!$scraperLogs->hasColumn('updated_at')) {
            $this->addSql('ALTER TABLE scraper_logs ADD updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL');
            $this->addSql('UPDATE scraper_logs SET updated_at = COALESCE(finished_at, started_at)');
        }
        if (!$operationStatuses->hasColumn('updated_at')) {
            $this->addSql('ALTER TABLE operation_statuses ADD updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL');
            $this->addSql('UPDATE operation_statuses SET updated_at = created_at');
        }

        $this->addSql('ALTER TABLE scraper_logs CHANGE created_at created_at DATETIME NOT NULL, CHANGE updated_at updated_at DATETIME NOT NULL');
        $this->addSql('ALTER TABLE operation_statuses CHANGE updated_at updated_at DATETIME NOT NULL');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE scraper_logs DROP created_at, DROP updated_at');
        $this->addSql('ALTER TABLE operation_statuses DROP updated_at');
    }
}
