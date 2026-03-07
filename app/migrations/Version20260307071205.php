<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * Auto-generated Migration: Please modify to your needs!
 */
final class Version20260307071205 extends AbstractMigration
{
    public function getDescription(): string
    {
        return '';
    }

    public function up(Schema $schema): void
    {
        // this up() migration is auto-generated, please modify it to your needs
        $this->addSql('ALTER TABLE ferry_companies CHANGE name name VARCHAR(255) NOT NULL, CHANGE website_url website_url VARCHAR(512) DEFAULT NULL, CHANGE scraper_class scraper_class VARCHAR(255) DEFAULT NULL, CHANGE active active TINYINT NOT NULL, CHANGE created_at created_at DATETIME NOT NULL, CHANGE updated_at updated_at DATETIME NOT NULL');
        $this->addSql('ALTER TABLE operation_statuses CHANGE status status VARCHAR(255) NOT NULL, CHANGE status_detail status_detail LONGTEXT DEFAULT NULL, CHANGE valid_date valid_date DATE NOT NULL, CHANGE scraped_at scraped_at DATETIME NOT NULL, CHANGE source_url source_url VARCHAR(512) DEFAULT NULL, CHANGE raw_html_hash raw_html_hash VARCHAR(64) DEFAULT NULL, CHANGE created_at created_at DATETIME NOT NULL');
        $this->addSql('ALTER TABLE routes CHANGE name name VARCHAR(255) NOT NULL, CHANGE active active TINYINT NOT NULL, CHANGE created_at created_at DATETIME NOT NULL, CHANGE updated_at updated_at DATETIME NOT NULL');
        $this->addSql('ALTER TABLE routes RENAME INDEX ferry_company_id TO IDX_32D5C2B3CF0A5E');
        $this->addSql('ALTER TABLE scraper_logs CHANGE status status VARCHAR(255) NOT NULL, CHANGE records_created records_created INT NOT NULL, CHANGE records_updated records_updated INT NOT NULL, CHANGE error_message error_message LONGTEXT DEFAULT NULL');
        $this->addSql('ALTER TABLE scraper_logs RENAME INDEX ferry_company_id TO IDX_2FBA52CF0A5E');
    }

    public function down(Schema $schema): void
    {
        // this down() migration is auto-generated, please modify it to your needs
        $this->addSql('ALTER TABLE ferry_companies CHANGE name name VARCHAR(255) NOT NULL COMMENT \'フェリー会社名\', CHANGE website_url website_url VARCHAR(512) DEFAULT NULL COMMENT \'公式サイトURL\', CHANGE scraper_class scraper_class VARCHAR(255) DEFAULT NULL COMMENT \'Pythonスクレイパークラス名\', CHANGE active active TINYINT DEFAULT 1 NOT NULL, CHANGE created_at created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, CHANGE updated_at updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL');
        $this->addSql('ALTER TABLE operation_statuses CHANGE status status ENUM(\'operating\', \'cancelled\', \'delayed\', \'suspended\', \'unknown\') DEFAULT \'unknown\' NOT NULL, CHANGE status_detail status_detail TEXT DEFAULT NULL COMMENT \'詳細理由 (例: 台風のため欠航)\', CHANGE valid_date valid_date DATE NOT NULL COMMENT \'この運航状況が適用される日付\', CHANGE scraped_at scraped_at DATETIME NOT NULL COMMENT \'スクレイピング実行日時\', CHANGE source_url source_url VARCHAR(512) DEFAULT NULL COMMENT \'スクレイピング元URL\', CHANGE raw_html_hash raw_html_hash VARCHAR(64) DEFAULT NULL COMMENT \'SHA-256 (重複スクレイピング防止)\', CHANGE created_at created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL');
        $this->addSql('ALTER TABLE routes CHANGE name name VARCHAR(255) NOT NULL COMMENT \'航路名 (例: 函館-青森)\', CHANGE active active TINYINT DEFAULT 1 NOT NULL, CHANGE created_at created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, CHANGE updated_at updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL');
        $this->addSql('ALTER TABLE routes RENAME INDEX idx_32d5c2b3cf0a5e TO ferry_company_id');
        $this->addSql('ALTER TABLE scraper_logs CHANGE status status ENUM(\'running\', \'success\', \'partial\', \'failed\') DEFAULT \'running\' NOT NULL, CHANGE records_created records_created INT DEFAULT 0 NOT NULL, CHANGE records_updated records_updated INT DEFAULT 0 NOT NULL, CHANGE error_message error_message TEXT DEFAULT NULL');
        $this->addSql('ALTER TABLE scraper_logs RENAME INDEX idx_2fba52cf0a5e TO ferry_company_id');
    }
}
