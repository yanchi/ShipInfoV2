-- ShipInfoV2 Seed Data
-- フェリー会社・航路マスタデータ
-- このファイルは MySQL コンテナ初回起動時に 01_schema.sql の直後に実行される

SET NAMES utf8mb4;
SET time_zone = '+09:00';

-- フェリー会社マスタ
-- created_at / updated_at は DEFAULT を持たないため明示的に指定する
INSERT INTO ferry_companies (id, name, website_url, scraper_class, active, created_at, updated_at)
VALUES
    (1, 'マルエーフェリー', 'https://www.aline-ferry.com', 'MarueFerry', 1, NOW(), NOW()),
    (2, 'マリックスライン', 'https://marixline.com',       'MarixLine',  1, NOW(), NOW())
ON DUPLICATE KEY UPDATE
    name          = VALUES(name),
    website_url   = VALUES(website_url),
    scraper_class = VALUES(scraper_class),
    active        = VALUES(active),
    updated_at    = NOW();

-- 航路マスタ（上り・下り別）
-- 下り = 鹿児島発 → 那覇着
-- 上り = 那覇発 → 鹿児島着
INSERT INTO routes (id, ferry_company_id, name, origin_port, destination_port, active, created_at, updated_at)
VALUES
    (1, 1, '鹿児島〜那覇（下り）', '鹿児島', '那覇', 1, NOW(), NOW()),
    (2, 1, '那覇〜鹿児島（上り）', '那覇',   '鹿児島', 1, NOW(), NOW()),
    (3, 2, '鹿児島〜那覇（下り）', '鹿児島', '那覇', 1, NOW(), NOW()),
    (4, 2, '那覇〜鹿児島（上り）', '那覇',   '鹿児島', 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE
    name             = VALUES(name),
    origin_port      = VALUES(origin_port),
    destination_port = VALUES(destination_port),
    active           = VALUES(active),
    updated_at       = NOW();
