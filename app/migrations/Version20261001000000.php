<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

/**
 * 出発港別の運航情報（specs/4-departure-port-status）。
 *
 * - ports / port_company_codes / route_stops / departure_statuses を作る
 * - routes.direction を足す
 * - 初期データ（港・別名・マルエーの港コード・direction・寄港順）を入れる
 *
 * 初期データはこのマイグレーションだけで入れる（docker/mysql/init には書かない）。
 * ID は決め打ちせず、routes や ferry_companies が空のテスト用 DB でも通るようにしている。
 */
final class Version20261001000000 extends AbstractMigration
{
    /** 港名 => 別名（research R5） */
    private const PORTS = [
        '鹿児島' => ['鹿児島新港', '鹿児島'],
        '名瀬'   => ['名瀬港', '名瀬'],
        '亀徳'   => ['亀徳新港', '亀徳港', '亀徳'],
        '和泊'   => ['和泊港', '和泊'],
        '与論'   => ['与論港', '与論'],
        '本部'   => ['本部港', '本部'],
        '那覇'   => ['那覇港', '那覇'],
    ];

    /** マルエーの便検索の港コード（research R3） */
    private const MARUE_CODES = [
        '鹿児島' => '50',
        '名瀬'   => '70',
        '亀徳'   => '78',
        '和泊'   => '80',
        '与論'   => '82',
        '本部'   => '84',
        '那覇'   => '83',
    ];

    /** 方向 => [港名, stop_order, day_offset]（data-model.md の route_stops） */
    private const STOPS = [
        'down' => [
            ['鹿児島', 1, 0], ['名瀬', 2, 1], ['亀徳', 3, 1], ['和泊', 4, 1],
            ['与論', 5, 1], ['本部', 6, 1], ['那覇', 7, 1],
        ],
        'up' => [
            ['那覇', 1, 0], ['本部', 2, 0], ['与論', 3, 0], ['和泊', 4, 0],
            ['亀徳', 5, 0], ['名瀬', 6, 0], ['鹿児島', 7, 1],
        ],
    ];

    public function getDescription(): string
    {
        return '出発港別の運航情報: ports / port_company_codes / route_stops / departure_statuses、routes.direction と初期データ';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE ports (id INT UNSIGNED AUTO_INCREMENT NOT NULL, name VARCHAR(64) NOT NULL, aliases JSON NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, UNIQUE INDEX UNIQ_899FD0CD5E237E06 (name), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('CREATE TABLE port_company_codes (id INT UNSIGNED AUTO_INCREMENT NOT NULL, external_code VARCHAR(32) NOT NULL, port_id INT UNSIGNED NOT NULL, ferry_company_id INT UNSIGNED NOT NULL, INDEX IDX_13454CAA76E92A9C (port_id), INDEX IDX_13454CAACF0A5E (ferry_company_id), UNIQUE INDEX uniq_port_company (port_id, ferry_company_id), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('CREATE TABLE route_stops (id INT UNSIGNED AUTO_INCREMENT NOT NULL, stop_order SMALLINT NOT NULL, day_offset SMALLINT DEFAULT 0 NOT NULL, route_id INT UNSIGNED NOT NULL, port_id INT UNSIGNED NOT NULL, INDEX IDX_A4CABD0A34ECB4E6 (route_id), INDEX IDX_A4CABD0A76E92A9C (port_id), UNIQUE INDEX uniq_route_port (route_id, port_id), UNIQUE INDEX uniq_route_stop_order (route_id, stop_order), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql("CREATE TABLE departure_statuses (id BIGINT UNSIGNED AUTO_INCREMENT NOT NULL, departure_date DATE NOT NULL, ship_name VARCHAR(255) DEFAULT '' NOT NULL, status VARCHAR(32) DEFAULT NULL, status_detail LONGTEXT DEFAULT NULL, scheduled_departure_at DATETIME DEFAULT NULL, scheduled_arrival_at DATETIME DEFAULT NULL, source_url VARCHAR(512) DEFAULT NULL, content_hash CHAR(64) NOT NULL, scraped_at DATETIME NOT NULL, checked_at DATETIME NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, route_id INT UNSIGNED NOT NULL, port_id INT UNSIGNED NOT NULL, operated_by_company_id INT UNSIGNED DEFAULT NULL, INDEX IDX_F78CBA4C34ECB4E6 (route_id), INDEX IDX_F78CBA4C76E92A9C (port_id), INDEX IDX_F78CBA4CBBA0F2E1 (operated_by_company_id), INDEX idx_departure_date_port (departure_date, port_id), UNIQUE INDEX uniq_departure (route_id, port_id, departure_date, ship_name), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4");
        $this->addSql('ALTER TABLE port_company_codes ADD CONSTRAINT FK_13454CAA76E92A9C FOREIGN KEY (port_id) REFERENCES ports (id)');
        $this->addSql('ALTER TABLE port_company_codes ADD CONSTRAINT FK_13454CAACF0A5E FOREIGN KEY (ferry_company_id) REFERENCES ferry_companies (id)');
        $this->addSql('ALTER TABLE route_stops ADD CONSTRAINT FK_A4CABD0A34ECB4E6 FOREIGN KEY (route_id) REFERENCES routes (id)');
        $this->addSql('ALTER TABLE route_stops ADD CONSTRAINT FK_A4CABD0A76E92A9C FOREIGN KEY (port_id) REFERENCES ports (id)');
        $this->addSql('ALTER TABLE departure_statuses ADD CONSTRAINT FK_F78CBA4C34ECB4E6 FOREIGN KEY (route_id) REFERENCES routes (id)');
        $this->addSql('ALTER TABLE departure_statuses ADD CONSTRAINT FK_F78CBA4C76E92A9C FOREIGN KEY (port_id) REFERENCES ports (id)');
        $this->addSql('ALTER TABLE departure_statuses ADD CONSTRAINT FK_F78CBA4CBBA0F2E1 FOREIGN KEY (operated_by_company_id) REFERENCES ferry_companies (id)');
        $this->addSql('ALTER TABLE routes ADD direction VARCHAR(8) DEFAULT NULL');

        // ── 初期データ ──────────────────────────────────────────
        // MySQL の NOW() はサーバーの TZ（UTC）になるので、PHP 側の JST を渡す
        $now = (new \DateTimeImmutable())->format('Y-m-d H:i:s');
        foreach (self::PORTS as $name => $aliases) {
            $this->addSql(
                'INSERT INTO ports (name, aliases, created_at, updated_at) VALUES (?, ?, ?, ?)',
                [$name, json_encode($aliases, JSON_UNESCAPED_UNICODE), $now, $now]
            );
        }

        // マルエーの会社があるときだけ入る（INSERT ... SELECT）
        foreach (self::MARUE_CODES as $name => $code) {
            $this->addSql(
                "INSERT INTO port_company_codes (port_id, ferry_company_id, external_code)
                 SELECT p.id, fc.id, ?
                 FROM ports p
                 JOIN ferry_companies fc ON fc.scraper_class = 'MarueFerry'
                 WHERE p.name = ?",
                [$code, $name]
            );
        }

        $this->addSql("UPDATE routes SET direction = 'down' WHERE origin_port = '鹿児島'");
        $this->addSql("UPDATE routes SET direction = 'up' WHERE origin_port = '那覇'");

        // direction の付いた航路ごとに寄港順を入れる（routes が空なら何も入らない）
        foreach (self::STOPS as $direction => $stops) {
            foreach ($stops as [$name, $order, $offset]) {
                $this->addSql(
                    'INSERT INTO route_stops (route_id, port_id, stop_order, day_offset)
                     SELECT r.id, p.id, ?, ?
                     FROM routes r
                     JOIN ports p ON p.name = ?
                     WHERE r.direction = ?',
                    [$order, $offset, $name, $direction]
                );
            }
        }
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE departure_statuses DROP FOREIGN KEY FK_F78CBA4C34ECB4E6');
        $this->addSql('ALTER TABLE departure_statuses DROP FOREIGN KEY FK_F78CBA4C76E92A9C');
        $this->addSql('ALTER TABLE departure_statuses DROP FOREIGN KEY FK_F78CBA4CBBA0F2E1');
        $this->addSql('ALTER TABLE route_stops DROP FOREIGN KEY FK_A4CABD0A34ECB4E6');
        $this->addSql('ALTER TABLE route_stops DROP FOREIGN KEY FK_A4CABD0A76E92A9C');
        $this->addSql('ALTER TABLE port_company_codes DROP FOREIGN KEY FK_13454CAA76E92A9C');
        $this->addSql('ALTER TABLE port_company_codes DROP FOREIGN KEY FK_13454CAACF0A5E');
        $this->addSql('DROP TABLE departure_statuses');
        $this->addSql('DROP TABLE route_stops');
        $this->addSql('DROP TABLE port_company_codes');
        $this->addSql('DROP TABLE ports');
        $this->addSql('ALTER TABLE routes DROP direction');
    }
}
