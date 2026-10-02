<?php

namespace App\Twig;

use Twig\Extension\AbstractExtension;
use Twig\TwigFunction;

/**
 * 全ページで使う Twig 関数（共通ヘッダーの会社一覧、最終確認時刻と古い情報の警告。FR-022・023）。
 * 中身は SiteRuntime（呼ばれたときにだけ作られる）。
 */
class SiteExtension extends AbstractExtension
{
    public function getFunctions(): array
    {
        return [
            new TwigFunction('site_freshness', [SiteRuntime::class, 'freshness']),
            new TwigFunction('site_companies', [SiteRuntime::class, 'companies']),
        ];
    }
}
