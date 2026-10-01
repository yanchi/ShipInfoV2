<?php

namespace App\Controller;

use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use App\Repository\OperationStatusRepository;
use App\Repository\RouteStopRepository;
use App\Service\PortAlertSummaryBuilder;
use App\Service\PortBoardBuilder;
use App\Service\PortFilterResolver;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class StatusController extends AbstractController
{
    #[Route('/', name: 'app_status_index')]
    public function index(OperationStatusRepository $operationStatusRepository): Response
    {
        $companies = $operationStatusRepository->findTodayByAllCompanies();

        return $this->render('status/index.html.twig', [
            'companies' => $companies,
            'today'     => new \DateTimeImmutable('today'),
        ]);
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

        if ($resolution->redirectTo !== null) {
            $response = new RedirectResponse($resolution->redirectTo);
        } else {
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
                'filter'      => $resolution->filter,
                'summary'     => $portAlertSummaryBuilder->build($fullBoard, $resolution->filter),
                'portOptions' => $portFilterResolver->departurePorts($boardStops),
                'today'       => $today,
                'now'         => new \DateTimeImmutable(),
            ]);
        }

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
