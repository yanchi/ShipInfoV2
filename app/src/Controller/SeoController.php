<?php

namespace App\Controller;

use App\Repository\FerryCompanyRepository;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\Routing\Generator\UrlGeneratorInterface;

/** 検索エンジン向け（robots.txt・sitemap.xml）。スキーム・ホストはリクエストのものを使う */
class SeoController extends AbstractController
{
    public function __construct(private readonly FerryCompanyRepository $companies)
    {
    }

    #[Route('/robots.txt', name: 'app_seo_robots', methods: ['GET'])]
    public function robots(Request $request): Response
    {
        $body = "User-agent: *\nAllow: /\n\nSitemap: {$request->getSchemeAndHttpHost()}/sitemap.xml\n";

        return new Response($body, Response::HTTP_OK, ['Content-Type' => 'text/plain; charset=UTF-8']);
    }

    #[Route('/sitemap.xml', name: 'app_seo_sitemap', methods: ['GET'])]
    public function sitemap(): Response
    {
        $urls = [
            ['loc' => $this->generateUrl('app_status_index', [], UrlGeneratorInterface::ABSOLUTE_URL), 'priority' => '1.0'],
            ['loc' => $this->generateUrl('app_status_ports', [], UrlGeneratorInterface::ABSOLUTE_URL), 'priority' => '0.9'],
        ];
        foreach ($this->companies->findActive() as $company) {
            $urls[] = [
                'loc'      => $this->generateUrl('app_status_company', ['id' => $company->getId()], UrlGeneratorInterface::ABSOLUTE_URL),
                'priority' => '0.8',
            ];
        }

        $response = $this->render('seo/sitemap.xml.twig', ['urls' => $urls]);
        $response->headers->set('Content-Type', 'application/xml; charset=UTF-8');

        return $response;
    }
}
