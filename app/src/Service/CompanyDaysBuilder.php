<?php

namespace App\Service;

use App\Entity\DepartureStatus;
use App\Entity\OperationStatus;
use App\Enum\CompanyDayStateEnum;
use App\Enum\OperationStatusEnum;
use App\View\CompanyDay;
use App\View\PortBoard;

/**
 * 会社別ページの日付ごとの表示（data-model の CompanyDay、research R13）。
 *
 * - 便あり：その会社のボード（PortBoard::forCompany）に行がある
 * - 便なし：行は無いが、その日その会社の no_service の行がある
 * - 情報なし：その日その会社の行が1つも無い
 */
class CompanyDaysBuilder
{
    /**
     * @param PortBoard $fullBoard 全港のボード（日付は表示する日付）
     * @param list<DepartureStatus> $statuses ボードを作った港別ステータス（全社分）
     * @param array<string, list<OperationStatus>> $routeSummaries [Y-m-d => その会社の航路単位の運航状況]
     * @return list<CompanyDay>
     */
    public function build(int $companyId, PortBoard $fullBoard, array $statuses, array $routeSummaries): array
    {
        // その会社の no_service の行がある日（便が無いと確認できた日）。
        // 便がある行（運航予定を含む）はボードに出るので、ボードに行が無くここにも無い日は「情報なし」
        /** @var array<string, true> $noServiceDates */
        $noServiceDates = [];
        foreach ($statuses as $s) {
            if ($s->getRoute()->getFerryCompany()->getId() === $companyId && $s->getStatus() === OperationStatusEnum::NoService) {
                $noServiceDates[$s->getDepartureDate()->format('Y-m-d')] = true;
            }
        }

        $days = [];
        foreach ($fullBoard->forCompany($companyId)->days as $day) {
            $key   = $day->date->format('Y-m-d');
            $state = match (true) {
                $day->directions !== []        => CompanyDayStateEnum::Services,
                isset($noServiceDates[$key])   => CompanyDayStateEnum::NoService,
                default                        => CompanyDayStateEnum::NoInfo,
            };

            // 航路単位では no_service（始発港を出る便が無い）でも、その方向の便が途中の港を出るなら要約行は出さない
            // （下の便の行と矛盾して見えるため。tasks T054a）
            $summaries = array_values(array_filter(
                $routeSummaries[$key] ?? [],
                static fn (OperationStatus $os) => !(
                    $os->getStatus() === OperationStatusEnum::NoService
                    && $os->getRoute()->getDirection() !== null
                    && $day->hasDeparturesOf($companyId, $os->getRoute()->getDirection())
                ),
            ));

            $days[] = new CompanyDay($day->date, $state, $summaries, $state === CompanyDayStateEnum::Services ? $day : null);
        }

        return $days;
    }
}
