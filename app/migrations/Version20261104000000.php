<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * 港のページ（/ports/{slug}）の URL に使う slug と、タイトル・見出しに使う呼び名 display_name を ports に足す。
 * スクレイパーは ports を読むだけなので、スクレイパー側は変えない（specs/18-port-seo-pages/data-model.md）。
 */
final class Version20261104000000 extends AbstractMigration
{
    private const PORTS = [
        '鹿児島' => ['kagoshima', null],
        '名瀬'   => ['naze', '奄美大島（名瀬港）'],
        '亀徳'   => ['kametoku', '徳之島（亀徳港）'],
        '和泊'   => ['wadomari', '沖永良部島（和泊港）'],
        '与論'   => ['yoron', '与論島（与論港）'],
        '本部'   => ['motobu', '沖縄・本部港'],
        '那覇'   => ['naha', null],
    ];

    public function getDescription(): string
    {
        return 'ports に slug・display_name を足す';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE ports ADD slug VARCHAR(32) DEFAULT NULL, ADD display_name VARCHAR(64) DEFAULT NULL');
        foreach (self::PORTS as $name => [$slug, $displayName]) {
            $this->addSql('UPDATE ports SET slug = ?, display_name = ? WHERE name = ?', [$slug, $displayName, $name]);
        }
        // 7 港以外（手で足した港など）で失敗しないよう、残りは port-<id> にする
        $this->addSql("UPDATE ports SET slug = CONCAT('port-', id) WHERE slug IS NULL");
        $this->addSql('ALTER TABLE ports MODIFY slug VARCHAR(32) NOT NULL');
        $this->addSql('CREATE UNIQUE INDEX UNIQ_899FD0CD989D9B62 ON ports (slug)');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('DROP INDEX UNIQ_899FD0CD989D9B62 ON ports');
        $this->addSql('ALTER TABLE ports DROP slug, DROP display_name');
    }
}
