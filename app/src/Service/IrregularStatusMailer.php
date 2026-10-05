<?php

namespace App\Service;

use App\Enum\NotificationResultEnum;
use App\View\IrregularService;
use App\View\NotificationOutcome;
use Symfony\Component\DependencyInjection\Attribute\Autowire;
use Symfony\Component\Mailer\Exception\TransportExceptionInterface;
use Symfony\Component\Mailer\MailerInterface;
use Symfony\Component\Mime\Email;
use Symfony\Component\Mime\Exception\ExceptionInterface as MimeExceptionInterface;
use Twig\Environment;

/**
 * 運航に変更がある便の通知メールを作って送る（specs/8-schedule-change-mail/contracts/notification-mail.md）。
 */
class IrregularStatusMailer
{
    /** V1 の件名（【ShipInfo】）と前方一致しないように V2 と付ける */
    public const SUBJECT_PREFIX = '【ShipInfo V2】';

    public function __construct(
        private readonly MailerInterface $mailer,
        private readonly Environment $twig,
        #[Autowire(env: 'MAILER_DSN')]
        private readonly string $mailerDsn,
        #[Autowire(env: 'NOTIFY_FROM')]
        private readonly string $from,
        #[Autowire(env: 'NOTIFY_TO')]
        private readonly string $to,
    ) {
    }

    public function subject(int $count): string
    {
        return sprintf('%s非通常運航ステータスを検出 (%d件)', self::SUBJECT_PREFIX, $count);
    }

    /**
     * @param list<IrregularService> $items
     */
    public function body(array $items): string
    {
        return $this->twig->render('email/irregular_statuses.txt.twig', ['items' => $items]);
    }

    /**
     * NOTIFY_TO をカンマで分け、前後の空白を除き、空のものを捨てた宛先。
     *
     * @return list<string>
     */
    public function recipients(): array
    {
        return array_values(array_filter(
            array_map('trim', explode(',', $this->to)),
            static fn (string $address): bool => $address !== '',
        ));
    }

    /** エラーの要約の長さの上限（notification_runs.error_message に入れる） */
    private const ERROR_SUMMARY_LENGTH = 1000;

    /**
     * 足りない設定の名前（MAILER_DSN・NOTIFY_FROM・NOTIFY_TO）。そろっていれば空。
     *
     * @return list<string>
     */
    public function missingSettings(): array
    {
        $missing = [];
        if (trim($this->mailerDsn) === '' || str_starts_with(trim($this->mailerDsn), 'null://')) {
            $missing[] = 'MAILER_DSN';
        }
        if (trim($this->from) === '') {
            $missing[] = 'NOTIFY_FROM';
        }
        if ($this->recipients() === []) {
            $missing[] = 'NOTIFY_TO';
        }

        return $missing;
    }

    /**
     * 設定が足りなければ送らず NotConfigured、送信で例外なら Failed を返す（どちらも例外は外に出さない）。
     *
     * @param list<IrregularService> $items
     */
    public function send(array $items): NotificationOutcome
    {
        $missing = $this->missingSettings();
        if ($missing !== []) {
            return new NotificationOutcome(NotificationResultEnum::NotConfigured, null, $missing);
        }

        try {
            $email = (new Email())
                ->from($this->from)
                ->to(...$this->recipients())
                ->subject($this->subject(count($items)))
                ->text($this->body($items));

            $this->mailer->send($email);
        } catch (TransportExceptionInterface|MimeExceptionInterface $e) {
            return new NotificationOutcome(NotificationResultEnum::Failed, $this->summarize($e));
        }

        return new NotificationOutcome(NotificationResultEnum::Sent);
    }

    /**
     * 例外のメッセージから、DSN の接続情報と宛先のアドレスを伏せた要約を作る。
     */
    private function summarize(\Throwable $e): string
    {
        $message = $e->getMessage();

        $secrets = [$this->mailerDsn, ...$this->recipients(), $this->from];
        // ユーザー名・パスワードは単独では伏せない（短い値が単語の途中を潰す）。DSN 全体・user:pass の組・URL 形式で伏せる
        $parts = parse_url($this->mailerDsn);
        if (is_array($parts) && ($parts['pass'] ?? '') !== '') {
            $secrets[] = ($parts['user'] ?? '') . ':' . $parts['pass'];
            $secrets[] = rawurldecode($parts['user'] ?? '') . ':' . rawurldecode($parts['pass']);
        }
        foreach (array_unique(array_filter($secrets, static fn (string $v): bool => $v !== '')) as $secret) {
            $message = str_replace($secret, '***', $message);
        }
        $message = (string) preg_replace('#([a-z][a-z0-9+.-]*://)[^/\s@]*@#i', '$1***@', $message);
        $message = (string) preg_replace('/[^\s<>,;"\']+@[^\s<>,;"\']+/', '***', $message);

        return mb_substr($message, 0, self::ERROR_SUMMARY_LENGTH);
    }
}
