<?php

namespace App\Tests\Service;

use App\Entity\FerryCompany;
use App\Entity\OperationStatus;
use App\Entity\Route;
use App\Enum\NotificationResultEnum;
use App\Enum\OperationStatusEnum;
use App\Enum\RouteDirectionEnum;
use App\Service\IrregularStatusMailer;
use App\View\IrregularPort;
use App\View\IrregularService;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;
use Symfony\Component\Mailer\Exception\TransportException;
use Symfony\Component\Mailer\MailerInterface;
use Symfony\Component\Mime\Email;
use Twig\Environment;
use Twig\Loader\FilesystemLoader;

class IrregularStatusMailerTest extends TestCase
{
    private function twig(): Environment
    {
        return new Environment(new FilesystemLoader(dirname(__DIR__, 2) . '/templates'), ['strict_variables' => true]);
    }

    private function mailer(MailerInterface $transport, string $dsn = 'smtp://mailer.test.invalid', string $from = 'noreply@example.com', string $to = ' a@example.com, ,b@example.com '): IrregularStatusMailer
    {
        return new IrregularStatusMailer($transport, $this->twig(), $dsn, $from, $to);
    }

    /**
     * @return list<IrregularService>
     */
    private function items(): array
    {
        $company = (new FerryCompany())->setName('マルエーフェリー');
        $route   = (new Route())->setFerryCompany($company)->setName('航路')->setDirection(RouteDirectionEnum::Down);
        $status  = (new OperationStatus())
            ->setRoute($route)
            ->setStatus(OperationStatusEnum::Cancelled)
            ->setStatusDetail('台風接近のため')
            ->setValidDate(new \DateTime('2026-10-07'));

        return [new IrregularService($company, $route, new \DateTimeImmutable('2026-10-07'), $status, [
            new IrregularPort('名瀬', 'フェリーなみのうえ', new \DateTime('2026-10-07 07:00'), OperationStatusEnum::Cancelled, '台風接近のため'),
            new IrregularPort('与論', 'フェリーなみのうえ', new \DateTime('2026-10-07 13:10'), OperationStatusEnum::Cancelled, null),
            new IrregularPort('本部', null, null, OperationStatusEnum::Delayed, null),
        ])];
    }

    public function testSendBuildsTextMailToAllRecipients(): void
    {
        $sent      = [];
        $transport = $this->createMock(MailerInterface::class);
        $transport->expects($this->once())->method('send')->willReturnCallback(static function (Email $email) use (&$sent): void {
            $sent[] = $email;
        });

        $outcome = $this->mailer($transport)->send($this->items());

        $this->assertSame(NotificationResultEnum::Sent, $outcome->result);
        $this->assertCount(1, $sent);
        $email = $sent[0];
        $this->assertSame('noreply@example.com', $email->getFrom()[0]->getAddress());
        $this->assertSame(['a@example.com', 'b@example.com'], array_map(static fn ($a) => $a->getAddress(), $email->getTo()));
        $this->assertSame('【ShipInfo V2】非通常運航ステータスを検出 (1件)', $email->getSubject());
        $this->assertNull($email->getHtmlBody());

        $body = (string) $email->getTextBody();
        $this->assertSame(<<<'TEXT'
以下の運航情報で通常運航以外のステータスが検出されました。

  会社名: マルエーフェリー
  運航日: 2026-10-07（水）
  方向　: 下り（那覇行き）
  状況　: 欠航
  備考　: 台風接近のため
  港　　:
    - 名瀬 07:00発 フェリーなみのうえ：欠航（台風接近のため）
    - 与論 13:10発 フェリーなみのうえ：欠航
    - 本部：条件付・遅延

TEXT, $body);
    }

    /** 港の行が抜港のとき「抜港（告知の文）」と出て、状況の行には抜港が出ない（US2 シナリオ1） */
    public function testSkippedPortIsLabeledSkipped(): void
    {
        $company = (new FerryCompany())->setName('マルエーフェリー');
        $route   = (new Route())->setFerryCompany($company)->setName('航路')->setDirection(RouteDirectionEnum::Down);
        $status  = (new OperationStatus())
            ->setRoute($route)
            ->setStatus(OperationStatusEnum::Operating)
            ->setValidDate(new \DateTime('2026-10-06'));
        $items = [new IrregularService($company, $route, new \DateTimeImmutable('2026-10-06'), $status, [
            new IrregularPort('与論', 'フェリー波之上', null, OperationStatusEnum::Skipped, '10月6日(火)与論港 抜港'),
        ])];

        $sent      = [];
        $transport = $this->createMock(MailerInterface::class);
        $transport->method('send')->willReturnCallback(static function (Email $email) use (&$sent): void {
            $sent[] = $email;
        });
        $this->mailer($transport)->send($items);

        $body = (string) $sent[0]->getTextBody();
        $this->assertStringContainsString('    - 与論 フェリー波之上：抜港（10月6日(火)与論港 抜港）', $body);
        $this->assertStringContainsString('  状況　: 通常運航（途中の港に変更あり）', $body);
    }

    /**
     * @return iterable<string, array{int}>
     */
    public static function counts(): iterable
    {
        yield '1件' => [1];
        yield '3件' => [3];
        yield '10件' => [10];
    }

    #[DataProvider('counts')]
    public function testSubjectIsDistinguishableFromV1(int $count): void
    {
        $subject = $this->mailer($this->createStub(MailerInterface::class))->subject($count);

        $this->assertStringStartsWith(IrregularStatusMailer::SUBJECT_PREFIX, $subject);
        $this->assertStringStartsWith('【ShipInfo V2】', $subject);
        $this->assertFalse(str_starts_with($subject, '【ShipInfo】'));
        $this->assertStringContainsString(sprintf('(%d件)', $count), $subject);
    }

    /**
     * @return iterable<string, array{string, string, string, string}>
     */
    public static function notConfigured(): iterable
    {
        yield 'DSN 空' => ['', 'noreply@example.com', 'a@example.com', 'MAILER_DSN'];
        yield 'DSN null' => ['null://null', 'noreply@example.com', 'a@example.com', 'MAILER_DSN'];
        yield 'FROM 空' => ['smtp://user:secret@mailer.test.invalid', '', 'a@example.com', 'NOTIFY_FROM'];
        yield 'TO 空' => ['smtp://user:secret@mailer.test.invalid', 'noreply@example.com', '', 'NOTIFY_TO'];
        yield 'TO カンマだけ' => ['smtp://user:secret@mailer.test.invalid', 'noreply@example.com', ' , ', 'NOTIFY_TO'];
    }

    #[DataProvider('notConfigured')]
    public function testMissingSettingsAreNotSent(string $dsn, string $from, string $to, string $missingName): void
    {
        $transport = $this->createMock(MailerInterface::class);
        $transport->expects($this->never())->method('send');

        $outcome = $this->mailer($transport, $dsn, $from, $to)->send($this->items());

        $this->assertSame(NotificationResultEnum::NotConfigured, $outcome->result);
        $this->assertSame([$missingName], $outcome->missingSettings);
        $this->assertStringNotContainsString('secret', implode(',', $outcome->missingSettings));
    }

    public function testTransportFailureIsReturnedWithoutSecrets(): void
    {
        $transport = $this->createStub(MailerInterface::class);
        $transport->method('send')->willThrowException(new TransportException(
            'Connection to "smtp://user:secret@mailer.test.invalid:587" refused (sending to a@example.com)',
        ));

        $outcome = $this->mailer($transport, 'smtp://user:secret@mailer.test.invalid:587')->send($this->items());

        $this->assertSame(NotificationResultEnum::Failed, $outcome->result);
        $this->assertNotNull($outcome->errorSummary);
        $this->assertStringContainsString('refused', $outcome->errorSummary);
        $this->assertStringNotContainsString('secret', $outcome->errorSummary);
        $this->assertStringNotContainsString('user:', $outcome->errorSummary);
        $this->assertStringNotContainsString('a@example.com', $outcome->errorSummary);
    }

    public function testErrorSummaryIsTruncated(): void
    {
        $transport = $this->createStub(MailerInterface::class);
        $transport->method('send')->willThrowException(new TransportException(str_repeat('x', 5000)));

        $outcome = $this->mailer($transport)->send($this->items());

        $this->assertSame(1000, mb_strlen((string) $outcome->errorSummary));
    }
}
