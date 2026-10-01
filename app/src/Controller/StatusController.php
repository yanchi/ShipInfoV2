<?php

namespace App\Controller;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Enum\DepartureDisplayStateEnum;
use App\Enum\OperationStatusEnum;
use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use App\Repository\OperationStatusRepository;
use App\Repository\RouteStopRepository;
use App\Service\PortAlertSummaryBuilder;
use App\Service\PortBoardBuilder;
use App\Service\PortFilterResolver;
use App\View\PortBoardDay;
use App\View\PortFilter;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class StatusController extends AbstractController
{
    #[Route('/', name: 'app_status_index')]
    public function index(
        Request $request,
        OperationStatusRepository $operationStatusRepository,
        RouteStopRepository $routeStopRepository,
        DepartureStatusRepository $departureStatusRepository,
        PortBoardBuilder $portBoardBuilder,
        PortFilterResolver $portFilterResolver,
        PortAlertSummaryBuilder $portAlertSummaryBuilder,
    ): Response {
        $today      = new \DateTimeImmutable('today');
        $boardStops = $routeStopRepository->findBoardStops();
        $fullBoard  = $portBoardBuilder->build(
            $boardStops,
            $departureStatusRepository->findForBoard($today, self::PORT_BOARD_DAYS),
            $today,
            self::PORT_BOARD_DAYS,
        );

        // トップはクエリを見ず Cookie だけを読む（保存・リダイレクトはしない）
        $resolution = $portFilterResolver->resolveFromCookie($request, $boardStops);
        $savedToday = $resolution->filter->isActive() ? ($fullBoard->filter($resolution->filter)->days[0] ?? null) : null;

        [$companies, $idleCompanies] = $this->splitIdleCompanies(
            $operationStatusRepository->findTodayByAllCompanies(),
            $fullBoard->days[0] ?? null,
        );

        $response = $this->render('status/index.html.twig', [
            // 要約は常に全港・4日分（Cookie では絞り込まない）
            'summary'       => $portAlertSummaryBuilder->build($fullBoard, PortFilter::none()),
            'portFilter'    => $resolution->filter,
            'portOptions'   => $portFilterResolver->departurePorts($boardStops),
            'savedToday'    => $savedToday,
            'companies'     => $companies,
            'idleCompanies' => $idleCompanies,
            'today'         => $today,
            'now'           => new \DateTimeImmutable(),
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
     * @return array{0: list<array{company: FerryCompany, routes: array<int, array{route: \App\Entity\Route, status: ?OperationStatus}>}>, 1: list<FerryCompany>}
     */
    private function splitIdleCompanies(array $companies, ?PortBoardDay $today): array
    {
        $companiesWithDepartures = [];
        foreach ($today?->directions ?? [] as $direction) {
            foreach ($direction->rows as $row) {
                foreach ($row->entries as $entry) {
                    if ($entry->companyId !== null && \in_array($entry->state, [DepartureDisplayStateEnum::Status, DepartureDisplayStateEnum::Scheduled], true)) {
                        $companiesWithDepartures[$entry->companyId] = true;
                    }
                }
            }
        }

        $active = [];
        $idle   = [];
        foreach ($companies as $companyData) {
            $routes  = $companyData['routes'];
            $running = array_filter(
                $routes,
                static fn (array $r) => $r['status']?->getStatus() !== OperationStatusEnum::NoService,
            );
            if ($routes !== [] && $running === [] && !isset($companiesWithDepartures[$companyData['company']->getId()])) {
                $idle[] = $companyData['company'];
            } else {
                $active[] = $companyData;
            }
        }

        return [$active, $idle];
    }

    #[Route('/company/{id}', name: 'app_status_company')]
    public function company(int $id, FerryCompanyRepository $ferryCompanyRepository, OperationStatusRepository $operationStatusRepository): Response
    {
        $company = $ferryCompanyRepository->find($id);
        if ($company === null) {
            throw $this->createNotFoundException("フェリー会社 ID:{$id} は存在しません。");
        }

        $statuses = $operationStatusRepository->findRecentByCompany($company, 3);

        return $this->render('status/company.html.twig', [
            'company'  => $company,
            'statuses' => $statuses,
        ]);
    }

    /** 港別ページに出す日数（今日〜3日先） */
    private const PORT_BOARD_DAYS = 4;

    #[Route('/ports', name: 'app_status_ports')]
    public function ports(
        Request $request,
        RouteStopRepository $routeStopRepository,
        DepartureStatusRepository $departureStatusRepository,
        PortBoardBuilder $portBoardBuilder,
        PortFilterResolver $portFilterResolver,
        PortAlertSummaryBuilder $portAlertSummaryBuilder,
    ): Response {
        $boardStops = $routeStopRepository->findBoardStops();
        $resolution = $portFilterResolver->resolve($request, $boardStops);

        $today     = new \DateTimeImmutable('today');
        $fullBoard = $portBoardBuilder->build(
            $boardStops,
            $departureStatusRepository->findForBoard($today, self::PORT_BOARD_DAYS),
            $today,
            self::PORT_BOARD_DAYS,
        );

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

    /** Cookie で中身が変わるページを共有キャッシュに載せない（research R15） */
    private function varyByCookie(Response $response): Response
    {
        $response->setPrivate();
        $response->setVary('Cookie', false);

        return $response;
    }
}
