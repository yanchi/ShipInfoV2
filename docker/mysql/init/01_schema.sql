-- ShipInfoV2 Initial Schema
-- Note: This file is for reference only.
-- The authoritative schema is managed by Doctrine Migrations (app/migrations/).
-- This file is executed only on first MySQL container startup.

SET NAMES utf8mb4;
SET time_zone = '+09:00';

CREATE TABLE IF NOT EXISTS ferry_companies (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT 'フェリー会社名',
    website_url VARCHAR(512) DEFAULT NULL COMMENT '公式サイトURL',
    scraper_class VARCHAR(255) DEFAULT NULL COMMENT 'Pythonスクレイパークラス名',
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS routes (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ferry_company_id INT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL COMMENT '航路名 (例: 函館-青森)',
    origin_port VARCHAR(255) DEFAULT NULL,
    destination_port VARCHAR(255) DEFAULT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (ferry_company_id) REFERENCES ferry_companies(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS operation_statuses (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    route_id INT UNSIGNED NOT NULL,
    status ENUM('operating','cancelled','delayed','suspended','unknown') NOT NULL DEFAULT 'unknown',
    status_detail TEXT DEFAULT NULL COMMENT '詳細理由 (例: 台風のため欠航)',
    departure_time DATETIME DEFAULT NULL,
    arrival_time DATETIME DEFAULT NULL,
    valid_date DATE NOT NULL COMMENT 'この運航状況が適用される日付',
    scraped_at DATETIME NOT NULL COMMENT 'スクレイピング実行日時',
    source_url VARCHAR(512) DEFAULT NULL COMMENT 'スクレイピング元URL',
    raw_html_hash VARCHAR(64) DEFAULT NULL COMMENT 'SHA-256 (重複スクレイピング防止)',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (route_id) REFERENCES routes(id),
    INDEX idx_route_date (route_id, valid_date),
    INDEX idx_date_status (valid_date, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scraper_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ferry_company_id INT UNSIGNED NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME DEFAULT NULL,
    status ENUM('running','success','partial','failed') NOT NULL DEFAULT 'running',
    records_created INT NOT NULL DEFAULT 0,
    records_updated INT NOT NULL DEFAULT 0,
    error_message TEXT DEFAULT NULL,
    FOREIGN KEY (ferry_company_id) REFERENCES ferry_companies(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
