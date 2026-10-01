<?php

namespace App\Controller;

use App\Repository\DepartureStatusRepository;
use App\Repository\FerryCompanyRepository;
use App\Repository\OperationStatusRepository;
use App\Repository\RouteStopRepository;
use App\Service\PortBoardBuilder;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
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
        RouteStopRepository $routeStopRepository,
        DepartureStatusRepository $departureStatusRepository,
        PortBoardBuilder $portBoardBuilder,
    ): Response {
        $today = new \DateTimeImmutable('today');

        $board = $portBoardBuilder->build(
            $routeStopRepository->findBoardStops(),
            $departureStatusRepository->findForBoard($today, self::PORT_BOARD_DAYS),
            $today,
            self::PORT_BOARD_DAYS,
        );

        return $this->render('status/ports.html.twig', [
            'board' => $board,
            'today' => $today,
        ]);
    }
}
