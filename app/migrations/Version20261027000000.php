<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * 臨時便の港の行に「この港を出たあと、運航の最後の港までに抜港があるか」を持つ skips_ports_after を足す。
 * 既存行は 0 から始まり、スクレイパーの次の回で書き直される（specs/16-extra-skip-flag/data-model.md）。
 */
final class Version20261027000000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'departure_statuses に skips_ports_after を足す';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE departure_statuses ADD skips_ports_after TINYINT(1) DEFAULT 0 NOT NULL');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE departure_statuses DROP skips_ports_after');
    }
}
