<?php

namespace App\Tests\Entity;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Entity\ScraperLog;
use App\Enum\OperationStatusEnum;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;

/**
 * scraper_logs・operation_statuses の created_at / updated_at（Version20261002000000）。
 * ScraperLog は HasLifecycleCallbacks が無く、PrePersist が呼ばれていなかった。
 */
class TimestampsTest extends KernelTestCase
{
    private EntityManagerInterface $em;
    private ?int $companyId = null;

    protected function setUp(): void
    {
        self::bootKernel();
        $this->em = static::getContainer()->get(EntityManagerInterface::class);

        $company = (new FerryCompany())->setName('タイムスタンプテスト会社')->setActive(true);
        $this->em->persist($company);
        $this->em->flush();
        $this->companyId = $company->getId();
    }

    protected function tearDown(): void
    {
        $conn = $this->em->getConnection();
        $conn->executeStatement('DELETE FROM scraper_logs WHERE ferry_company_id = ?', [$this->companyId]);
        $conn->executeStatement('DELETE os FROM operation_statuses os JOIN routes r ON r.id = os.route_id WHERE r.ferry_company_id = ?', [$this->companyId]);
        $conn->executeStatement('DELETE FROM routes WHERE ferry_company_id = ?', [$this->companyId]);
        $conn->executeStatement('DELETE FROM ferry_companies WHERE id = ?', [$this->companyId]);
        parent::tearDown();
    }

    public function testScraperLogSetsTimestampsOnPersistAndUpdate(): void
    {
        $log = (new ScraperLog())->setFerryCompany($this->em->getReference(FerryCompany::class, $this->companyId));
        $this->em->persist($log);
        $this->em->flush();

        $this->assertNotNull($log->getStartedAt());
        $this->assertNotNull($log->getCreatedAt());
        $this->assertEquals($log->getCreatedAt(), $log->getUpdatedAt());

        $createdAt = $log->getCreatedAt();
        $log->setErrorMessage('更新');
        $this->em->flush();

        $this->assertSame($createdAt, $log->getCreatedAt());
        $this->assertGreaterThan($createdAt, $log->getUpdatedAt());
    }

    public function testOperationStatusSetsUpdatedAtOnPersistAndUpdate(): void
    {
        $route = (new Route())
            ->setFerryCompany($this->em->getReference(FerryCompany::class, $this->companyId))
            ->setName('タイムスタンプテスト航路')
            ->setActive(true);
        $status = (new OperationStatus())
            ->setRoute($route)
            ->setStatus(OperationStatusEnum::Operating)
            ->setValidDate(new \DateTime('today'));
        $this->em->persist($route);
        $this->em->persist($status);
        $this->em->flush();

        $this->assertEquals($status->getCreatedAt(), $status->getUpdatedAt());

        $createdAt = $status->getCreatedAt();
        $status->setStatus(OperationStatusEnum::Cancelled);
        $this->em->flush();

        $this->assertSame($createdAt, $status->getCreatedAt());
        $this->assertGreaterThan($createdAt, $status->getUpdatedAt());
    }
}
