<?php

namespace App\DataFixtures;

use App\Entity\DepartureStatus;
use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Port;
use App\Entity\PortCompanyCode;
use App\Entity\Route;
use App\Entity\RouteStop;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
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
 *
 * 港別ページ（/ports）用に、マイグレーション Version20261001000000 と同じ港・港コード・寄港順・direction
 * を入れ直す（fixtures:load はこれらのテーブルも purge するため）。あわせて目視確認用の港別ステータスを作る。
 * dev DB 向けのデータなので、PHPUnit（APP_ENV=test の _test DB）では使われない。
 * 自動テストは各テストが必要なデータを自分で作成する。
 *
 * WARNING: doctrine:fixtures:load は実行前に全テーブルを purge する。
 *          スクレイパーが収集した実データも消えるため、開発環境でのみ実行すること。
 */
class AppFixtures extends Fixture
{
    private const SOURCE_URL = 'https://example.invalid/fixtures';

    /** 港名 => 別名（マイグレーションと同じ） */
    private const PORTS = [
        '鹿児島' => ['鹿児島新港', '鹿児島'],
        '名瀬'   => ['名瀬港', '名瀬'],
        '亀徳'   => ['亀徳新港', '亀徳港', '亀徳'],
        '和泊'   => ['和泊港', '和泊'],
        '与論'   => ['与論港', '与論'],
        '本部'   => ['本部港', '本部'],
        '那覇'   => ['那覇港', '那覇'],
    ];

    private const MARUE_CODES = [
        '鹿児島' => '50', '名瀬' => '70', '亀徳' => '78', '和泊' => '80',
        '与論'   => '82', '本部' => '84', '那覇' => '83',
    ];

    /** 方向 => [港名, day_offset] の寄港順 */
    private const STOPS = [
        'down' => [['鹿児島', 0], ['名瀬', 1], ['亀徳', 1], ['和泊', 1], ['与論', 1], ['本部', 1], ['那覇', 1]],
        'up'   => [['那覇', 0], ['本部', 0], ['与論', 0], ['和泊', 0], ['亀徳', 0], ['名瀬', 0], ['鹿児島', 1]],
    ];

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

        $routeEntities = [];
        foreach ($routes as [$company, $name, $origin, $destination, $status, $detail]) {
            $route = $this->makeRoute($company, $name, $origin, $destination);
            $manager->persist($route);
            $manager->persist($this->makeStatus($route, $status, $detail, $today));
            $routeEntities[] = $route;
        }

        [$marueDown, $marueUp, $marixDown, $marixUp] = $routeEntities;
        $ports                                       = $this->loadPorts($manager, $marue, $routeEntities);
        $this->loadDepartures($manager, $ports, $marix, $marueDown, $marueUp, $marixDown, $marixUp);

        $manager->flush();
    }

    /**
     * 港・マルエーの港コード・寄港順を入れる。
     *
     * @param Route[] $routes
     *
     * @return array<string, Port>
     */
    private function loadPorts(ObjectManager $manager, FerryCompany $marue, array $routes): array
    {
        $ports = [];
        foreach (self::PORTS as $name => $aliases) {
            $ports[$name] = (new Port())->setName($name)->setAliases($aliases);
            $manager->persist($ports[$name]);
            $manager->persist((new PortCompanyCode())
                ->setPort($ports[$name])
                ->setFerryCompany($marue)
                ->setExternalCode(self::MARUE_CODES[$name]));
        }

        foreach ($routes as $route) {
            foreach (self::STOPS[$route->getDirection()->value] as $i => [$name, $offset]) {
                $manager->persist((new RouteStop())
                    ->setRoute($route)
                    ->setPort($ports[$name])
                    ->setStopOrder($i + 1)
                    ->setDayOffset($offset));
            }
        }

        return $ports;
    }

    /**
     * /ports の目視確認用の港別ステータス。
     * - 今日: マルエー運航（通常運航）、マリックスは no_service（他社運航の目印なし）→ マルエーだけ出る
     * - 明日: マリックス運航。マリックスの行は無く、マルエーの行で operated_by だけ分かっている → 「マリックスライン／運航予定」
     * - 3日先: マルエー status NULL → 「運航予定」
     *
     * @param array<string, Port> $ports
     */
    private function loadDepartures(
        ObjectManager $manager,
        array $ports,
        FerryCompany $marix,
        Route $marueDown,
        Route $marueUp,
        Route $marixDown,
        Route $marixUp,
    ): void {
        $today    = new \DateTimeImmutable('today');
        $tomorrow = $today->modify('+1 day');
        $day3     = $today->modify('+3 days');

        // 今日の下り鹿児島発・上り那覇発（マルエー）と、マリックスの no_service
        $manager->persist($this->makeDeparture($marueDown, $ports['鹿児島'], $today, 'フェリー波之上', OperationStatusEnum::Operating, $today->setTime(18, 0), $tomorrow->setTime(19, 0)));
        $manager->persist($this->makeDeparture($marueUp, $ports['那覇'], $today, 'フェリーあけぼの', OperationStatusEnum::Delayed, $today->setTime(7, 0), $tomorrow->setTime(8, 30), '和泊港・与論港は条件付寄港。'));
        $manager->persist($this->makeDeparture($marixDown, $ports['鹿児島'], $today, '', OperationStatusEnum::NoService));
        $manager->persist($this->makeDeparture($marixUp, $ports['那覇'], $today, '', OperationStatusEnum::NoService));

        // 明日はマリックス運航（マルエーの検索で分かっているだけ）
        foreach ([[$marueDown, '鹿児島'], [$marueUp, '那覇']] as [$route, $port]) {
            $manager->persist($this->makeDeparture($route, $ports[$port], $tomorrow, '', OperationStatusEnum::NoService, operatedBy: $marix));
        }

        // 3日先の名瀬発はマルエーの運航予定
        $manager->persist($this->makeDeparture($marueDown, $ports['名瀬'], $day3, 'フェリーあけぼの', null, $day3->setTime(5, 50), $day3->setTime(19, 0)));
    }

    private function makeDeparture(
        Route $route,
        Port $port,
        \DateTimeImmutable $date,
        string $shipName,
        ?OperationStatusEnum $status,
        ?\DateTimeImmutable $departureAt = null,
        ?\DateTimeImmutable $arrivalAt = null,
        ?string $detail = null,
        ?FerryCompany $operatedBy = null,
    ): DepartureStatus {
        return (new DepartureStatus())
            ->setRoute($route)
            ->setPort($port)
            ->setDepartureDate(\DateTime::createFromImmutable($date))
            ->setShipName($shipName)
            ->setStatus($status)
            ->setStatusDetail($detail)
            ->setScheduledDepartureAt($departureAt ? \DateTime::createFromImmutable($departureAt) : null)
            ->setScheduledArrivalAt($arrivalAt ? \DateTime::createFromImmutable($arrivalAt) : null)
            ->setOperatedByCompany($operatedBy)
            ->setSourceUrl(self::SOURCE_URL)
            ->setContentHash(hash('sha256', $route->getName() . $port->getName() . $date->format('Y-m-d') . $shipName))
            ->setCheckedAt(new \DateTime());
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
            ->setDirection($origin === '鹿児島' ? RouteDirectionEnum::Down : RouteDirectionEnum::Up)
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
