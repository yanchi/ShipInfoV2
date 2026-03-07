<?php

namespace App\Controller;

use App\Repository\FerryCompanyRepository;
use App\Repository\OperationStatusRepository;
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
}
