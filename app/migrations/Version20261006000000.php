<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * 運航の変更の通知メールの確認回（日付 × 時刻枠）を持つ notification_runs を作る。
 * (run_date, slot) の一意キーで、同じ回を二重に送らない（specs/8-schedule-change-mail/data-model.md）。
 */
final class Version20261006000000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'notification_runs を作る';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE notification_runs (id INT UNSIGNED AUTO_INCREMENT NOT NULL, run_date DATE NOT NULL, slot SMALLINT UNSIGNED NOT NULL, result VARCHAR(32) NOT NULL, item_count INT UNSIGNED NOT NULL, error_message LONGTEXT DEFAULT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, UNIQUE INDEX uniq_notification_run (run_date, slot), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('DROP TABLE notification_runs');
    }
}
