<?php

namespace App\Tests\View;

use App\Entity\Port;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\View\PortBoard;
use App\View\PortBoardDay;
use App\View\PortBoardDirection;
use App\View\PortBoardEntry;
use App\View\PortBoardRow;
use App\View\PortFilter;
use PHPUnit\Framework\TestCase;

class PortBoardTest extends TestCase
{
    public function testCommonCheckedAtWhenAllSameMinute(): void
    {
        $direction = $this->direction(RouteDirectionEnum::Down, [
            $this->row(1, [$this->entry('2026-10-01 06:00:05')]),
            $this->row(2, [$this->entry('2026-10-01 06:00:40'), $this->entry(null)]),
        ]);

        $this->assertSame('2026-10-01 06:00:05', $direction->commonCheckedAt()?->format('Y-m-d H:i:s'));
    }

    public function testCommonCheckedAtIsNullWhenOneDiffers(): void
    {
        $direction = $this->direction(RouteDirectionEnum::Down, [
            $this->row(1, [$this->entry('2026-10-01 06:00')]),
            $this->row(2, [$this->entry('2026-10-01 06:15')]),
        ]);

        $this->assertNull($direction->commonCheckedAt());
    }

    public function testCommonCheckedAtIsNullWithoutCheckedAt(): void
    {
        $direction = $this->direction(RouteDirectionEnum::Down, [$this->row(1, [$this->entry(null)])]);

        $this->assertNull($direction->commonCheckedAt());
    }

    public function testLastCheckedAt(): void
    {
        $board = new PortBoard([
            new PortBoardDay(new \DateTimeImmutable('2026-10-01'), [
                $this->direction(RouteDirectionEnum::Down, [$this->row(1, [$this->entry('2026-10-01 06:00')])]),
            ]),
            new PortBoardDay(new \DateTimeImmutable('2026-10-02'), [
                $this->direction(RouteDirectionEnum::Up, [$this->row(1, [$this->entry('2026-10-01 07:30'), $this->entry(null)])]),
            ]),
        ]);

        $this->assertSame('2026-10-01 07:30', $board->lastCheckedAt()?->format('Y-m-d H:i'));
        $this->assertNull((new PortBoard([]))->lastCheckedAt());
    }

    public function testFirstExtraDepartureOfPicksEarliestExtraOfCompanyAndDirection(): void
    {
        $extra = static fn (int $companyId, string $departure, OperationStatusEnum $status = OperationStatusEnum::Extra): PortBoardEntry => new PortBoardEntry(
            DepartureDisplayStateEnum::Status,
            $status,
            departureAt: new \DateTimeImmutable($departure),
            companyId: $companyId,
        );
        $day = new PortBoardDay(new \DateTimeImmutable('2026-10-26'), [
            $this->direction(RouteDirectionEnum::Down, [
                $this->row(1, [$extra(1, '2026-10-26 16:00'), $extra(2, '2026-10-26 01:00')]),
                $this->row(3, [$extra(1, '2026-10-26 03:50'), $extra(1, '2026-10-26 00:30', OperationStatusEnum::Operating)]),
            ]),
            $this->direction(RouteDirectionEnum::Up, [
                $this->row(7, [$extra(1, '2026-10-26 05:00')]),
            ]),
        ]);

        // 出港時刻がいちばん早い Extra（出港済みでも）。ほかの会社・Extra 以外は見ない
        $down = $day->firstExtraDepartureOf(1, RouteDirectionEnum::Down);
        $this->assertNotNull($down);
        $this->assertSame('港3', $down->portName);
        $this->assertSame('03:50', $down->departureAt->format('H:i'));
        $this->assertSame('港7', $day->firstExtraDepartureOf(1, RouteDirectionEnum::Up)?->portName);
        $this->assertSame('港1', $day->firstExtraDepartureOf(2, RouteDirectionEnum::Down)?->portName);
        $this->assertNull($day->firstExtraDepartureOf(2, RouteDirectionEnum::Up));
        $this->assertNull($day->firstExtraDepartureOf(9, RouteDirectionEnum::Down));
    }

    public function testFilterByPortKeepsThatPortInEachDirection(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(5));

        foreach ($board->days as $day) {
            $this->assertSame(
                ['down' => [5], 'up' => [5]],
                $this->portIdsByDirection($day),
            );
        }
    }

    public function testFilterByPortDropsDirectionWithoutThatPort(): void
    {
        // 鹿児島(1) は下りにしか無い
        $board = $this->sampleBoard()->filter(new PortFilter(1));

        $this->assertSame(['down' => [1]], $this->portIdsByDirection($board->days[0]));
    }

    public function testFilterByDirection(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(direction: RouteDirectionEnum::Up));

        $this->assertSame(['up' => [7, 5, 3]], $this->portIdsByDirection($board->days[0]));
    }

    public function testFilterByPortAndDirection(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(5, RouteDirectionEnum::Down));

        $this->assertSame(['down' => [5]], $this->portIdsByDirection($board->days[1]));
    }

    public function testFilterKeepsAllDays(): void
    {
        $board = $this->sampleBoard()->filter(new PortFilter(999));

        $this->assertCount(2, $board->days);
        $this->assertSame([], $board->days[0]->directions);
    }

    public function testFilterNoneReturnsSameBoard(): void
    {
        $board = $this->sampleBoard();

        $this->assertEquals($board, $board->filter(PortFilter::none()));
    }

    public function testForCompanyKeepsOnlyThatCompanysServices(): void
    {
        $board = new PortBoard([
            new PortBoardDay(new \DateTimeImmutable('2026-10-01'), [
                $this->direction(RouteDirectionEnum::Down, [
                    // 自社の発表済み・他社の発表済み → 自社だけ残る
                    $this->row(1, [$this->service(1), $this->service(2)]),
                    // 他社だけ → 行ごと落ちる
                    $this->row(3, [$this->service(2)]),
                    // 自社の運航予定 → 残る
                    $this->row(5, [$this->service(1, DepartureDisplayStateEnum::Scheduled)]),
                ]),
                // 情報なし・便なしだけ → 方向ごと落ちる
                $this->direction(RouteDirectionEnum::Up, [
                    $this->row(7, [new PortBoardEntry(DepartureDisplayStateEnum::NoInfo, companyId: 1)]),
                    $this->row(5, [new PortBoardEntry(DepartureDisplayStateEnum::NoService)]),
                ]),
            ]),
            new PortBoardDay(new \DateTimeImmutable('2026-10-02'), [
                $this->direction(RouteDirectionEnum::Down, [$this->row(1, [$this->service(2)])]),
            ]),
        ]);

        $company = $board->forCompany(1);

        $this->assertSame(['down' => [1, 5]], $this->portIdsByDirection($company->days[0]));
        $this->assertCount(1, $company->days[0]->directions[0]->rows[0]->entries);
        $this->assertSame(1, $company->days[0]->directions[0]->rows[0]->entries[0]->companyId);
        // 日付は残る
        $this->assertCount(2, $company->days);
        $this->assertSame([], $company->days[1]->directions);
    }

    public function testHasDeparturesOf(): void
    {
        $day = new PortBoardDay(new \DateTimeImmutable('2026-10-01'), [
            $this->direction(RouteDirectionEnum::Down, [$this->row(1, [$this->service(1)])]),
            $this->direction(RouteDirectionEnum::Up, [$this->row(7, [new PortBoardEntry(DepartureDisplayStateEnum::NoInfo, companyId: 2)])]),
        ]);

        $this->assertTrue($day->hasDeparturesOf(1));
        $this->assertTrue($day->hasDeparturesOf(1, RouteDirectionEnum::Down));
        $this->assertFalse($day->hasDeparturesOf(1, RouteDirectionEnum::Up));
        // 情報なし（他社運航の今日の行）は便として数えない
        $this->assertFalse($day->hasDeparturesOf(2));
    }

    // ------------------------------------------------------------------
    // extraSkipsPortsOf()（15-extra-voyage-badge FR-004）。
    // 下りの港を6つ（添字 0〜5：鹿児島・名瀬・亀徳・和泊・与論・本部）並べたボードを手で組む。
    // 添字 1 = 名瀬、2 = 亀徳、3 = 和泊、4 = 与論、5 = 本部
    // ------------------------------------------------------------------

    /** US2-1：名瀬・本部の臨時便。亀徳・和泊・与論に同じ船の行が無い */
    public function testExtraSkipsPortsWhenMidwayPortsHaveNoRowOfSameShip(): void
    {
        $board = $this->extraBoard([[
            1 => [$this->extra('波之上', '03:50', '13:50')],
            5 => [$this->extra('波之上', '12:00', '13:50')],
        ]]);

        $this->assertTrue($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** US2-3（上り）：那覇・名瀬が臨時便、あいだの港は同じ船の欠航 */
    public function testExtraSkipsPortsWhenMidwayPortsAreCancelledOfSameShip(): void
    {
        $cancelled = fn (string $time) => new PortBoardEntry(DepartureDisplayStateEnum::Status, OperationStatusEnum::Cancelled, shipName: 'クロス', departureAt: new \DateTimeImmutable("2026-10-27 {$time}"), arrivalAt: new \DateTimeImmutable('2026-10-28 09:00'), companyId: 1);
        // 上りの並び：那覇・本部・与論・和泊・亀徳・名瀬
        $board = $this->extraBoard([[
            0 => [$this->extra('クロス', '07:00', '09:00', arrivalDay: '2026-10-28')],
            1 => [$cancelled('08:00')],
            2 => [$cancelled('10:00')],
            3 => [$cancelled('12:00')],
            4 => [$cancelled('14:00')],
            5 => [$this->extra('クロス', '21:20', '09:00', arrivalDay: '2026-10-28')],
        ]]);

        $this->assertTrue($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** US2-2：名瀬だけの臨時便は、最初と最後が同じなので抜港なし */
    public function testExtraDoesNotSkipPortsWhenOnlyOnePortHasExtra(): void
    {
        $board = $this->extraBoard([[1 => [$this->extra('クロス', '05:50', '17:00')]]]);

        $this->assertFalse($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    public function testExtraDoesNotSkipPortsWhenCallingAtEveryPort(): void
    {
        $rows = [];
        foreach ([1, 2, 3, 4, 5] as $i) {
            $rows[$i] = [$this->extra('波之上', '0' . $i . ':00', '13:50')];
        }

        $this->assertFalse($this->extraBoard([$rows])->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 便検索とぶつかった港（同じ船の運航予定・通常運航の行）は寄港として数える */
    public function testExtraCountsScheduledAndOperatingRowsOfSameShipAsCalling(): void
    {
        $at   = new \DateTimeImmutable('2026-10-27 09:00');
        $rows = [
            1 => [$this->extra('波之上', '03:50', '13:50')],
            2 => [new PortBoardEntry(DepartureDisplayStateEnum::Scheduled, shipName: '波之上', departureAt: $at, companyId: 1)],
            3 => [new PortBoardEntry(DepartureDisplayStateEnum::Status, OperationStatusEnum::Operating, shipName: '波之上', departureAt: $at, companyId: 1)],
            4 => [new PortBoardEntry(DepartureDisplayStateEnum::Status, OperationStatusEnum::Extra, shipName: '波之上', departureAt: $at, arrivalAt: new \DateTimeImmutable('2026-10-27 13:50'), companyId: 1)],
            5 => [$this->extra('波之上', '12:00', '13:50')],
        ];

        $this->assertFalse($this->extraBoard([$rows])->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 日をまたぐ運航：今日 22:00 名瀬、明日 06:00 亀徳・10:00 与論、和泊は行なし */
    public function testExtraSkipsPortsAcrossDays(): void
    {
        $board = $this->extraBoard([
            [1 => [$this->extra('波之上', '22:00', '13:00', arrivalDay: '2026-10-28')]],
            [
                2 => [$this->extra('波之上', '06:00', '13:00', day: '2026-10-28', arrivalDay: '2026-10-28')],
                4 => [$this->extra('波之上', '10:00', '13:00', day: '2026-10-28', arrivalDay: '2026-10-28')],
            ],
        ]);

        $this->assertTrue($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 明日だけの臨時便は今日の運航ではないので見ない */
    public function testExtraOnlyTomorrowIsIgnored(): void
    {
        $board = $this->extraBoard([
            [],
            [
                1 => [$this->extra('波之上', '03:50', '13:50', day: '2026-10-28', arrivalDay: '2026-10-28')],
                5 => [$this->extra('波之上', '12:00', '13:50', day: '2026-10-28', arrivalDay: '2026-10-28')],
            ],
        ]);

        $this->assertFalse($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 運航が2つあって、どちらかに抜港があれば true */
    public function testExtraSkipsPortsWhenOneOfTwoVoyagesSkips(): void
    {
        $rows = [];
        foreach ([1, 2, 3, 4, 5] as $i) {
            $rows[$i][] = $this->extra('波之上', '0' . $i . ':00', '13:50');
        }
        $rows[1][] = $this->extra('クロス', '05:00', '17:00');
        $rows[5][] = $this->extra('クロス', '12:00', '17:00');

        $this->assertTrue($this->extraBoard([$rows])->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 同じ船が今日2回出る：到着予定が違うので別の運航。2回目の鹿児島〜名瀬のあいだは抜港にならない */
    public function testExtraSeparatesTwoVoyagesOfSameShipByArrival(): void
    {
        $second = [
            0 => [$this->extra('波之上', '18:00', '09:00', arrivalDay: '2026-10-28')],
            1 => [$this->extra('波之上', '23:00', '09:00', arrivalDay: '2026-10-28')],
        ];
        $first = [
            2 => [$this->extra('波之上', '08:00', '13:50')],
            3 => [$this->extra('波之上', '09:00', '13:50')],
            4 => [$this->extra('波之上', '10:00', '13:50')],
        ];
        $firstEnds = [
            1 => [$this->extra('波之上', '03:50', '13:50')],
            5 => [$this->extra('波之上', '12:00', '13:50')],
        ];

        // 1回目の亀徳・和泊・与論が全部 Extra：どちらの運航も抜港なし
        $this->assertFalse($this->extraBoard([$this->mergeRows($second, $first, $firstEnds)])->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
        // 1回目の亀徳・和泊・与論が行なし：1回目が抜港
        $this->assertTrue($this->extraBoard([$this->mergeRows($second, $firstEnds)])->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 日が離れた同じ船の臨時便（今日 名瀬、2日後 本部）は別の運航。つなげて抜港にしない */
    public function testExtraDoesNotJoinDistantVoyagesOfSameShip(): void
    {
        $board = $this->extraBoard([
            [1 => [$this->extra('クロス', '05:50', '17:00')]],
            [],
            [5 => [$this->extra('クロス', '10:00', '12:00', day: '2026-10-29', arrivalDay: '2026-10-29')]],
        ]);

        $this->assertFalse($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    /** 船名や到着予定が分からないエントリーはまとめない（抜港あり、と言わない側に倒す） */
    public function testExtraWithoutShipNameOrArrivalIsNotGrouped(): void
    {
        $noShip = $this->extraBoard([[
            1 => [$this->extra(null, '03:50', '13:50')],
            5 => [$this->extra(null, '12:00', '13:50')],
        ]]);
        $noArrival = $this->extraBoard([[
            1 => [$this->extra('波之上', '03:50', null)],
            5 => [$this->extra('波之上', '12:00', null)],
        ]]);

        $this->assertFalse($noShip->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
        $this->assertFalse($noArrival->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
    }

    public function testExtraOfOtherCompanyIsIgnored(): void
    {
        $board = $this->extraBoard([[
            1 => [$this->extra('波之上', '03:50', '13:50', companyId: 2)],
            5 => [$this->extra('波之上', '12:00', '13:50', companyId: 2)],
        ]]);

        $this->assertFalse($board->extraSkipsPortsOf(1, RouteDirectionEnum::Down));
        $this->assertTrue($board->extraSkipsPortsOf(2, RouteDirectionEnum::Down));
    }

    // ------------------------------------------------------------------

    /**
     * 日ごとに「港の添字 => エントリー」を渡して、6港の下りのボードを組む（今日 = 2026-10-27）。
     * 渡さない港の行はエントリーなし（臨時便は寄らない港の行を作らない）。
     *
     * @param list<array<int, list<PortBoardEntry>>> $days
     */
    private function extraBoard(array $days): PortBoard
    {
        $result = [];
        foreach ($days as $i => $entriesByPort) {
            $rows = [];
            foreach (range(0, 5) as $port) {
                $rows[] = $this->row($port + 1, $entriesByPort[$port] ?? []);
            }
            $result[] = new PortBoardDay(
                (new \DateTimeImmutable('2026-10-27'))->modify("+{$i} days"),
                [$this->direction(RouteDirectionEnum::Down, $rows)],
            );
        }

        return new PortBoard($result);
    }

    /** 臨時便のエントリー。$arrival が null なら到着予定なし */
    private function extra(?string $ship, string $time, ?string $arrival, string $day = '2026-10-27', string $arrivalDay = '2026-10-27', int $companyId = 1): PortBoardEntry
    {
        return new PortBoardEntry(
            DepartureDisplayStateEnum::Status,
            OperationStatusEnum::Extra,
            shipName: $ship,
            departureAt: new \DateTimeImmutable("{$day} {$time}"),
            arrivalAt: $arrival === null ? null : new \DateTimeImmutable("{$arrivalDay} {$arrival}"),
            companyId: $companyId,
        );
    }

    /**
     * @param array<int, list<PortBoardEntry>> ...$parts
     *
     * @return array<int, list<PortBoardEntry>>
     */
    private function mergeRows(array ...$parts): array
    {
        $rows = [];
        foreach ($parts as $part) {
            foreach ($part as $port => $entries) {
                $rows[$port] = [...($rows[$port] ?? []), ...$entries];
            }
        }

        return $rows;
    }

    private function service(int $companyId, DepartureDisplayStateEnum $state = DepartureDisplayStateEnum::Status): PortBoardEntry
    {
        return new PortBoardEntry(
            $state,
            $state === DepartureDisplayStateEnum::Status ? OperationStatusEnum::Operating : null,
            companyId: $companyId,
        );
    }

    /** 2日分。下り：1・3・5 → 7、上り：7・5・3 → 1 */
    private function sampleBoard(): PortBoard
    {
        $days = [];
        foreach (['2026-10-01', '2026-10-02'] as $date) {
            $days[] = new PortBoardDay(new \DateTimeImmutable($date), [
                $this->direction(RouteDirectionEnum::Down, array_map(fn (int $id) => $this->row($id, [$this->entry(null)]), [1, 3, 5])),
                $this->direction(RouteDirectionEnum::Up, array_map(fn (int $id) => $this->row($id, [$this->entry(null)]), [7, 5, 3])),
            ]);
        }

        return new PortBoard($days);
    }

    /** @return array<string, list<int>> */
    private function portIdsByDirection(PortBoardDay $day): array
    {
        $result = [];
        foreach ($day->directions as $direction) {
            $result[$direction->direction->value] = array_map(static fn (PortBoardRow $r) => $r->port->getId(), $direction->rows);
        }

        return $result;
    }

    /** @param list<PortBoardRow> $rows */
    private function direction(RouteDirectionEnum $direction, array $rows): PortBoardDirection
    {
        return new PortBoardDirection($direction, '那覇', $rows);
    }

    /** @param list<PortBoardEntry> $entries */
    private function row(int $portId, array $entries): PortBoardRow
    {
        return new PortBoardRow($this->port($portId), $entries);
    }

    private function entry(?string $checkedAt): PortBoardEntry
    {
        return new PortBoardEntry(
            DepartureDisplayStateEnum::NoService,
            checkedAt: $checkedAt !== null ? new \DateTimeImmutable($checkedAt) : null,
        );
    }

    private function port(int $id): Port
    {
        $port = (new Port())->setName('港' . $id);
        (new \ReflectionProperty($port, 'id'))->setValue($port, $id);

        return $port;
    }
}
