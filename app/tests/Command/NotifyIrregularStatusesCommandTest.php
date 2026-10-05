<?php

namespace App\Tests\Command;

use App\Command\NotifyIrregularStatusesCommand;
use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Repository\NotificationRunRepository;
use App\Service\IrregularServiceCollector;
use App\Service\IrregularStatusMailer;
use App\Service\NotificationSlotResolver;
use Doctrine\DBAL\Connection;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Console\Application;
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;
use Symfony\Bundle\FrameworkBundle\Test\MailerAssertionsTrait;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Tester\CommandTester;
use Symfony\Component\Mailer\Exception\TransportException;
use Symfony\Component\Mailer\MailerInterface;
use Symfony\Component\Mime\Email;
use Twig\Environment;

class NotifyIrregularStatusesCommandTest extends KernelTestCase
{
    use MailerAssertionsTrait;

    private EntityManagerInterface $em;
    private Connection $conn;
    private \DateTimeImmutable $today;
    private ?int $companyId = null;

    protected function setUp(): void
    {
        self::bootKernel();
        $this->em    = static::getContainer()->get(EntityManagerInterface::class);
        $this->conn  = $this->em->getConnection();
        $this->today = new \DateTimeImmutable('today');
        $this->clearWindow();
    }

    protected function tearDown(): void
    {
        $this->removeCompany();
        $this->clearWindow();
        parent::tearDown();
    }

    /** テスト DB（_test の別 DB）の今日〜3日先の行と今日の回を消し、ほかのテスト・seed に件数が左右されないようにする */
    private function clearWindow(): void
    {
        $from = $this->today->format('Y-m-d');
        $to   = $this->today->modify('+3 days')->format('Y-m-d');
        $this->conn->executeStatement('DELETE FROM operation_statuses WHERE valid_date BETWEEN ? AND ?', [$from, $to]);
        $this->conn->executeStatement('DELETE FROM departure_statuses WHERE departure_date BETWEEN ? AND ?', [$from, $to]);
        $this->conn->executeStatement('DELETE FROM notification_runs WHERE run_date = ?', [$from]);
    }

    private function removeCompany(): void
    {
        if ($this->companyId === null) {
            return;
        }
        $this->conn->executeStatement('DELETE os FROM operation_statuses os JOIN routes r ON r.id = os.route_id WHERE r.ferry_company_id = ?', [$this->companyId]);
        $this->conn->executeStatement('DELETE FROM routes WHERE ferry_company_id = ?', [$this->companyId]);
        $this->conn->executeStatement('DELETE FROM ferry_companies WHERE id = ?', [$this->companyId]);
        $this->companyId = null;
    }

    private function createStatus(OperationStatusEnum $status, ?string $detail = null): void
    {
        $company = (new FerryCompany())->setName('通知コマンドテスト会社')->setActive(true);
        $route   = (new Route())->setFerryCompany($company)->setName('通知コマンドテスト航路')->setDirection(RouteDirectionEnum::Down)->setActive(true);
        $this->em->persist($company);
        $this->em->persist($route);
        $this->em->persist((new OperationStatus())
            ->setRoute($route)
            ->setStatus($status)
            ->setStatusDetail($detail)
            ->setValidDate(\DateTime::createFromImmutable($this->today))
            ->setScrapedAt(new \DateTime())
            ->setSourceUrl('https://example.invalid/test'));
        $this->em->flush();
        $this->companyId = $company->getId();
    }

    /**
     * @param array<string, mixed> $input
     */
    private function runCommand(array $input): CommandTester
    {
        $application = new Application(self::$kernel);
        $tester      = new CommandTester($application->find('app:notify-irregular-statuses'));
        $tester->execute($input);

        return $tester;
    }

    private function runResult(int $slot): ?string
    {
        $value = $this->conn->fetchOne('SELECT result FROM notification_runs WHERE run_date = ? AND slot = ?', [$this->today->format('Y-m-d'), $slot]);

        return $value === false ? null : (string) $value;
    }

    public function testSendsOneMailAndSkipsSecondRun(): void
    {
        $this->createStatus(OperationStatusEnum::Cancelled, '台風接近のため');

        $first = $this->runCommand(['--slot' => '6']);

        $this->assertSame(Command::SUCCESS, $first->getStatusCode());
        $this->assertEmailCount(1);
        /** @var Email $email */
        $email = $this->getMailerMessage();
        $this->assertStringStartsWith('【ShipInfo V2】', (string) $email->getSubject());
        $this->assertSame('【ShipInfo V2】非通常運航ステータスを検出 (1件)', $email->getSubject());
        $this->assertStringContainsString('通知コマンドテスト会社', (string) $email->getTextBody());
        $this->assertStringContainsString('台風接近のため', (string) $email->getTextBody());
        $this->assertSame('sent', $this->runResult(6));
        $this->assertSame(1, (int) $this->conn->fetchOne('SELECT item_count FROM notification_runs WHERE run_date = ? AND slot = 6', [$this->today->format('Y-m-d')]));

        $second = $this->runCommand(['--slot' => '6']);

        $this->assertSame(Command::SUCCESS, $second->getStatusCode());
        $this->assertStringContainsString('6時の回は処理済みです', $second->getDisplay());
        $this->assertEmailCount(1);
    }

    public function testNoIrregularStatusSendsNothing(): void
    {
        $this->createStatus(OperationStatusEnum::Operating);

        $tester = $this->runCommand(['--slot' => '6']);

        $this->assertSame(Command::SUCCESS, $tester->getStatusCode());
        $this->assertEmailCount(0);
        $this->assertSame('none', $this->runResult(6));
    }

    public function testDryRunPrintsMailWithoutSendingOrRecording(): void
    {
        $this->createStatus(OperationStatusEnum::Cancelled);

        $tester = $this->runCommand(['--slot' => '6', '--dry-run' => true]);

        $this->assertSame(Command::SUCCESS, $tester->getStatusCode());
        $this->assertStringContainsString('【ShipInfo V2】非通常運航ステータスを検出 (1件)', $tester->getDisplay());
        $this->assertStringContainsString('通知コマンドテスト会社', $tester->getDisplay());
        $this->assertEmailCount(0);
        $this->assertNull($this->runResult(6));
    }

    public function testInvalidSlotIsRejected(): void
    {
        $tester = $this->runCommand(['--slot' => '7']);

        $this->assertSame(Command::INVALID, $tester->getStatusCode());
        $this->assertEmailCount(0);
        $this->assertNull($this->runResult(7));
    }

    /** 送信で例外 → failed・終了コード 1。同じ回は再送しない */
    public function testTransportFailureIsRecordedAndNotRetried(): void
    {
        $this->createStatus(OperationStatusEnum::Cancelled);

        $transport = $this->createStub(MailerInterface::class);
        $transport->method('send')->willThrowException(new TransportException('Connection refused'));
        $mailer  = new IrregularStatusMailer($transport, static::getContainer()->get(Environment::class), 'smtp://mailer.test.invalid', 'noreply@example.com', 'ops@example.com');
        $command = new NotifyIrregularStatusesCommand(
            static::getContainer()->get(NotificationRunRepository::class),
            static::getContainer()->get(IrregularServiceCollector::class),
            new NotificationSlotResolver(),
            $mailer,
        );

        $tester = new CommandTester($command);
        $tester->execute(['--slot' => '15']);

        $this->assertSame(Command::FAILURE, $tester->getStatusCode());
        $this->assertStringContainsString('Connection refused', $tester->getDisplay());
        $this->assertSame('failed', $this->runResult(15));
        $this->assertSame('Connection refused', $this->conn->fetchOne('SELECT error_message FROM notification_runs WHERE run_date = ? AND slot = 15', [$this->today->format('Y-m-d')]));

        $again = new CommandTester($command);
        $again->execute(['--slot' => '15']);

        $this->assertSame(Command::SUCCESS, $again->getStatusCode());
        $this->assertStringContainsString('処理済みです', $again->getDisplay());
    }

    /** 設定が足りない → 警告・not_configured・終了コード 0 */
    public function testMissingSettingsAreWarnedAndRecorded(): void
    {
        $this->createStatus(OperationStatusEnum::Cancelled);

        $mailer  = new IrregularStatusMailer($this->createMock(MailerInterface::class), static::getContainer()->get(Environment::class), 'smtp://mailer.test.invalid', 'noreply@example.com', '');
        $command = new NotifyIrregularStatusesCommand(
            static::getContainer()->get(NotificationRunRepository::class),
            static::getContainer()->get(IrregularServiceCollector::class),
            new NotificationSlotResolver(),
            $mailer,
        );

        $tester = new CommandTester($command);
        $tester->execute(['--slot' => '1']);

        $this->assertSame(Command::SUCCESS, $tester->getStatusCode());
        $this->assertStringContainsString('NOTIFY_TO が未設定のためメールを送りませんでした', preg_replace('/\s+/', ' ', $tester->getDisplay()) ?? '');
        $this->assertSame('not_configured', $this->runResult(1));
    }
}
