<?php

namespace App\DataFixtures;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Enum\OperationStatusEnum;
use Doctrine\Bundle\FixturesBundle\Fixture;
use Doctrine\Persistence\ObjectManager;

/**
 * 開発・テスト用のシードデータ。
 *
 * 会社・航路のマスタは docker/mysql/init/02_seed.sql と同じ内容を投入する
 * （02_seed.sql は MySQL ボリューム初回作成時にしか実行されないため、
 *   既存ボリュームに対してはこちらで再投入する）。
 * 加えて、表示確認用に航路0件のダミー会社を1社追加する（02_seed.sql には含めない）。
 *
 * 運航状況は当日分を4種（通常運航・条件付遅延・欠航・便なし）作成し、Twig のバッジ分岐を
 * 目視で確認できるようにする（運休・不明は含まない）。
 * dev DB 向けのデータなので、PHPUnit（APP_ENV=test の _test DB）では使われない。
 * 自動テストは各テストが必要なデータを自分で作成する。
 *
 * WARNING: doctrine:fixtures:load は実行前に全テーブルを purge する。
 *          スクレイパーが収集した実データも消えるため、開発環境でのみ実行すること。
 */
class AppFixtures extends Fixture
{
    private const SOURCE_URL = 'https://example.invalid/fixtures';

    public function load(ObjectManager $manager): void
    {
        // Doctrine の date / datetime 型は DateTimeImmutable を受け付けないため DateTime を使う
        $today = new \DateTime('today');

        $marue = $this->makeCompany('マルエーフェリー', 'https://www.aline-ferry.com', 'MarueFerry');
        $marix = $this->makeCompany('マリックスライン', 'https://marixline.com', 'MarixLine');

        // 航路0件の会社。トップページの3列表示と「航路情報がありません。」の目視確認用。
        // scraper_class を持たないためスクレイパーの実行対象にはならない
        $noRoutes = (new FerryCompany())
            ->setName('サンプル汽船（航路未設定）')
            ->setActive(true);

        $manager->persist($marue);
        $manager->persist($marix);
        $manager->persist($noRoutes);

        // 下り = 鹿児島発 → 那覇着 / 上り = 那覇発 → 鹿児島着
        $routes = [
            [$marue, '鹿児島〜那覇（下り）', '鹿児島', '那覇', OperationStatusEnum::Operating, null],
            [$marue, '那覇〜鹿児島（上り）', '那覇', '鹿児島', OperationStatusEnum::Cancelled, '台風接近のため欠航'],
            [$marix, '鹿児島〜那覇（下り）', '鹿児島', '那覇', OperationStatusEnum::Delayed, '波浪のため条件付き運航'],
            [$marix, '那覇〜鹿児島（上り）', '那覇', '鹿児島', OperationStatusEnum::NoService, null],
        ];

        foreach ($routes as [$company, $name, $origin, $destination, $status, $detail]) {
            $route = $this->makeRoute($company, $name, $origin, $destination);
            $manager->persist($route);
            $manager->persist($this->makeStatus($route, $status, $detail, $today));
        }

        $manager->flush();
    }

    private function makeCompany(string $name, string $websiteUrl, string $scraperClass): FerryCompany
    {
        return (new FerryCompany())
            ->setName($name)
            ->setWebsiteUrl($websiteUrl)
            ->setScraperClass($scraperClass)
            ->setActive(true);
    }

    private function makeRoute(FerryCompany $company, string $name, string $origin, string $destination): Route
    {
        return (new Route())
            ->setFerryCompany($company)
            ->setName($name)
            ->setOriginPort($origin)
            ->setDestinationPort($destination)
            ->setActive(true);
    }

    private function makeStatus(
        Route $route,
        OperationStatusEnum $status,
        ?string $detail,
        \DateTime $validDate,
    ): OperationStatus {
        return (new OperationStatus())
            ->setRoute($route)
            ->setStatus($status)
            ->setStatusDetail($detail)
            ->setValidDate($validDate)
            ->setScrapedAt(new \DateTime())
            ->setSourceUrl(self::SOURCE_URL);
    }
}
