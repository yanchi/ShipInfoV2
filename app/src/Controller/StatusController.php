<?php

namespace App\Controller;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use App\Repository\OperationStatusRepository;
use App\Repository\RouteStopRepository;
use App\Service\CompanyDaysBuilder;
use App\Service\PortAlertSummaryBuilder;
use App\Service\PortBoardBuilder;
use App\Service\PortFilterResolver;
use App\View\PortBoard;
use App\View\PortBoardDay;
use App\View\PortBoardEntry;
use App\View\PortFilter;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class StatusController extends AbstractController
{
    /** 港別ページ・トップのボードに出す日数（今日〜3日先） */
    private const PORT_BOARD_DAYS = 4;

    public function __construct(
        private readonly DepartureStatusRepository $departureStatusRepository,
        private readonly PortBoardBuilder $portBoardBuilder,
    ) {
    }

    #[Route('/', name: 'app_status_index')]
    public function index(
        Request $request,
        OperationStatusRepository $operationStatusRepository,
        RouteStopRepository $routeStopRepository,
        PortFilterResolver $portFilterResolver,
        PortAlertSummaryBuilder $portAlertSummaryBuilder,
    ): Response {
        $today      = new \DateTimeImmutable('today');
        $boardStops = $routeStopRepository->findBoardStops();
        $fullBoard  = $this->buildFullBoard($boardStops, $today);

        // トップはクエリを見ず Cookie だけを読む（保存・リダイレクトはしない）
        $resolution = $portFilterResolver->resolveFromCookie($request, $boardStops);
        $savedToday = $resolution->filter->isActive() ? ($fullBoard->filter($resolution->filter)->days[0] ?? null) : null;

        [$companies, $idleCompanies] = $this->splitIdleCompanies(
            $operationStatusRepository->findTodayByAllCompanies(),
            $fullBoard->days[0] ?? null,
        );

        $response = $this->render('status/index.html.twig', [
            // 要約は常に全港・4日分（Cookie では絞り込まない）
            'summary'               => $portAlertSummaryBuilder->build($fullBoard, PortFilter::none()),
            'portFilter'            => $resolution->filter,
            'portOptions'           => $portFilterResolver->departurePorts($boardStops),
            'savedToday'            => $savedToday,
            'companies'             => $companies,
            'idleCompanies'         => $idleCompanies,
            'routesDepartingMidway' => $this->routesDepartingMidway($companies, $fullBoard->days[0] ?? null),
            'today'                 => $today,
            'now'                   => new \DateTimeImmutable(),
        ]);

        if ($resolution->cookie !== null) {
            $response->headers->setCookie($resolution->cookie);
        }

        return $this->varyByCookie($response);
    }

    /**
     * 本日運航なしの会社を分ける（FR-018）。航路がすべて no_service で、今日の港別ボードにもその会社の便が無い会社。
     *
     * 航路単位の no_service は「始発港を今日出る便が無い」という意味で、前日に始発港を出た便が今日途中の港を出ることがある。
     * だから港別ボードの便（発表済み・運航予定）も見る。航路が無い会社・情報なしの航路がある会社はカードのまま。
     *
     * @param array<int, array{company: FerryCompany, routes: array<int, array{route: \App\Entity\Route, status: ?OperationStatus}>}> $companies
     *
     * @return array{0: list<array{company: FerryCompany, routes: array<int, array{route: \App\Entity\Route, status: ?OperationStatus}>}>, 1: list<FerryCompany>}
     */
    private function splitIdleCompanies(array $companies, ?PortBoardDay $today): array
    {
        $active = [];
        $idle   = [];
        foreach ($companies as $companyData) {
            $routes  = $companyData['routes'];
            $running = array_filter(
                $routes,
                static fn (array $r) => $r['status']?->getStatus() !== OperationStatusEnum::NoService,
            );
            if ($routes !== [] && $running === [] && !$today?->hasDeparturesOf($companyData['company']->getId())) {
                $idle[] = $companyData['company'];
            } else {
                $active[] = $companyData;
            }
        }

        return [$active, $idle];
    }

    /**
     * 航路単位では no_service でも、今日その方向の便が途中の港を出る航路（会社カードで「— 便なし」と出さない。tasks T054a）。
     *
     * 前日に始発港を出た便が今日途中の港を出る日は、その区間（始発港を除いた港を出る便）の状態を出す。
     * 全便が同じ状態ならそれを badge。バラけていて欠航・運休・条件付・遅延が混じれば changed（スケジュール変更）、
     * 混じらなければ通常運航 → 不明 → 運航予定の順で badge。
     *
     * @param list<array{company: FerryCompany, routes: array<int, array{route: \App\Entity\Route, status: ?OperationStatus}>}> $companies
     *
     * @return array<int, array{kind: 'changed'|'badge', state: ?DepartureDisplayStateEnum, status: ?OperationStatusEnum}> [routeId => 表示]
     */
    private function routesDepartingMidway(array $companies, ?PortBoardDay $today): array
    {
        $result = [];
        foreach ($companies as $companyData) {
            $companyId = $companyData['company']->getId();
            foreach ($companyData['routes'] as $routeId => $r) {
                $direction = $r['route']->getDirection();
                if ($today === null || $direction === null || $r['status']?->getStatus() !== OperationStatusEnum::NoService) {
                    continue;
                }
                $display = $this->midwayDisplay($today->midwayDeparturesOf($companyId, $direction));
                if ($display !== null) {
                    $result[$routeId] = $display;
                }
            }
        }

        return $result;
    }

    /**
     * @param list<PortBoardEntry> $entries
     *
     * @return array{kind: 'changed'|'badge', state: ?DepartureDisplayStateEnum, status: ?OperationStatusEnum}|null 便が無ければ null
     */
    private function midwayDisplay(array $entries): ?array
    {
        if ($entries === []) {
            return null;
        }
        // 全部同じ状態ならそれを出す（途中の港が1つで欠航なら「欠航」）
        $first = $entries[0];
        if (array_filter($entries, static fn (PortBoardEntry $e) => $e->state !== $first->state || $e->status !== $first->status) === []) {
            return ['kind' => 'badge', 'state' => $first->state === DepartureDisplayStateEnum::Scheduled ? $first->state : null, 'status' => $first->status];
        }
        // 状態がバラけていて、欠航・運休・条件付・遅延が混じる
        if (array_filter($entries, static fn (PortBoardEntry $e) => $e->isAlert()) !== []) {
            return ['kind' => 'changed', 'state' => null, 'status' => null];
        }

        $statuses = array_map(static fn (PortBoardEntry $e) => $e->status, $entries);
        foreach ([OperationStatusEnum::Operating, OperationStatusEnum::Unknown] as $status) {
            if (\in_array($status, $statuses, true)) {
                return ['kind' => 'badge', 'state' => null, 'status' => $status];
            }
        }

        return ['kind' => 'badge', 'state' => DepartureDisplayStateEnum::Scheduled, 'status' => null];
    }

    #[Route('/company/{id}', name: 'app_status_company')]
    public function company(
        int $id,
        FerryCompanyRepository $ferryCompanyRepository,
        OperationStatusRepository $operationStatusRepository,
        RouteStopRepository $routeStopRepository,
        CompanyDaysBuilder $companyDaysBuilder,
    ): Response {
        $company = $ferryCompanyRepository->find($id);
        // 無効な会社は港別ボードにも共通ヘッダーにも出ないので、ページも出さない
        if ($company === null || !$company->isActive()) {
            throw $this->createNotFoundException("フェリー会社 ID:{$id} は存在しません。");
        }

        $today    = new \DateTimeImmutable('today');
        $statuses = $this->departureStatusRepository->findForBoard($today, self::PORT_BOARD_DAYS);

        return $this->render('status/company.html.twig', [
            'company' => $company,
            'days'    => $companyDaysBuilder->build(
                $company->getId(),
                $this->buildFullBoard($routeStopRepository->findBoardStops(), $today, $statuses),
                $statuses,
                $operationStatusRepository->findUpcomingByCompany($company, $today, self::PORT_BOARD_DAYS),
            ),
            'now' => new \DateTimeImmutable(),
        ]);
    }

    #[Route('/ports', name: 'app_status_ports')]
    public function ports(
        Request $request,
        RouteStopRepository $routeStopRepository,
        PortFilterResolver $portFilterResolver,
        PortAlertSummaryBuilder $portAlertSummaryBuilder,
    ): Response {
        $boardStops = $routeStopRepository->findBoardStops();
        $resolution = $portFilterResolver->resolve($request, $boardStops);

        $today     = new \DateTimeImmutable('today');
        $fullBoard = $this->buildFullBoard($boardStops, $today);

        $response = $this->render('status/ports.html.twig', [
            'board'       => $fullBoard->filter($resolution->filter),
            'fullBoard'   => $fullBoard,
            'portFilter'  => $resolution->filter,
            'summary'     => $portAlertSummaryBuilder->build($fullBoard, $resolution->filter),
            'portOptions' => $portFilterResolver->departurePorts($boardStops),
            'today'       => $today,
            'now'         => new \DateTimeImmutable(),
        ]);

        if ($resolution->cookie !== null) {
            $response->headers->setCookie($resolution->cookie);
        }

        return $this->varyByCookie($response);
    }

    /** 港別ページの絞り込みフォーム。表示・保存・保存を解除のどれも GET /ports にリダイレクトする（PRG） */
    #[Route('/ports/filter', name: 'app_status_ports_filter', methods: ['POST'])]
    public function portsFilter(
        Request $request,
        RouteStopRepository $routeStopRepository,
        PortFilterResolver $portFilterResolver,
    ): Response {
        $resolution = $portFilterResolver->submit(
            $request,
            $routeStopRepository->findBoardStops(),
            $this->isCsrfTokenValid(PortFilterResolver::COOKIE_NAME, (string) $request->request->get('_token')),
        );

        $response = new RedirectResponse($resolution->redirectTo ?? $this->generateUrl('app_status_ports'), Response::HTTP_SEE_OTHER);
        if ($resolution->cookie !== null) {
            $response->headers->setCookie($resolution->cookie);
        }

        return $this->varyByCookie($response);
    }

    /**
     * 全港・今日〜3日先のボード。$statuses を渡せばそれで作る（会社別ページは同じ行を日付の状態の判定にも使うため）。
     *
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<\App\Entity\Port>, arrivalPort: \App\Entity\Port}> $boardStops
     * @param list<\App\Entity\DepartureStatus>|null $statuses
     */
    private function buildFullBoard(array $boardStops, \DateTimeImmutable $today, ?array $statuses = null): PortBoard
    {
        return $this->portBoardBuilder->build(
            $boardStops,
            $statuses ?? $this->departureStatusRepository->findForBoard($today, self::PORT_BOARD_DAYS),
            $today,
            self::PORT_BOARD_DAYS,
        );
    }

    /** Cookie で中身が変わるページを共有キャッシュに載せない（research R15） */
    private function varyByCookie(Response $response): Response
    {
        $response->setPrivate();
        $response->setVary('Cookie', false);

        return $response;
    }
}
