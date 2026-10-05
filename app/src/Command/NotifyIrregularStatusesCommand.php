<?php

namespace App\Command;

use App\Enum\NotificationResultEnum;
use App\Repository\NotificationRunRepository;
use App\Service\IrregularServiceCollector;
use App\Service\IrregularStatusMailer;
use App\Service\NotificationSlotResolver;
use Symfony\Component\Console\Attribute\AsCommand;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Input\InputOption;
use Symfony\Component\Console\Output\OutputInterface;
use Symfony\Component\Console\Style\SymfonyStyle;

/**
 * 運航に変更がある便をメールで知らせる（specs/8-schedule-change-mail/contracts/console-command.md）。
 */
#[AsCommand(name: 'app:notify-irregular-statuses', description: '運航に変更がある便をメールで知らせる')]
class NotifyIrregularStatusesCommand extends Command
{
    /** notification_runs を残す日数 */
    private const RETENTION_DAYS = 90;

    public function __construct(
        private readonly NotificationRunRepository $runRepository,
        private readonly IrregularServiceCollector $collector,
        private readonly NotificationSlotResolver $slotResolver,
        private readonly IrregularStatusMailer $mailer,
    ) {
        parent::__construct();
    }

    protected function configure(): void
    {
        $this
            ->addOption('slot', null, InputOption::VALUE_REQUIRED, '確認の回（1・6・15）。指定すると時刻の窓を見ない')
            ->addOption('dry-run', null, InputOption::VALUE_NONE, '件名・本文を出すだけ（回を確保しない・送らない・行を消さない）');
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $io     = new SymfonyStyle($input, $output);
        $now    = new \DateTimeImmutable('now');
        $today  = new \DateTimeImmutable('today');
        $dryRun = (bool) $input->getOption('dry-run');

        $slotOption = $input->getOption('slot');
        if ($slotOption !== null) {
            try {
                $slot = $this->slotResolver->fromOption((string) $slotOption);
            } catch (\InvalidArgumentException $e) {
                $io->error($e->getMessage());

                return Command::INVALID;
            }
        } else {
            $slot = $this->slotResolver->resolve($now);
            if ($slot === null) {
                $io->writeln(sprintf('確認時刻ではありません（現在 %s）', $now->format('H:i')));

                return Command::SUCCESS;
            }
        }

        $label = sprintf('%s %d時', $today->format('Y-m-d'), $slot);

        if ($dryRun) {
            return $this->dryRun($io, $today, $label);
        }

        if (!$this->runRepository->claim($today, $slot)) {
            $io->writeln(sprintf('%sの回は処理済みです', $label));

            return Command::SUCCESS;
        }

        $items = $this->collector->collect($today);
        if ($items === []) {
            $this->runRepository->finish($today, $slot, NotificationResultEnum::None, 0, null);
            $io->writeln(sprintf('%s：通常運航以外の便はありません', $label));
            $this->cleanup($today);

            return Command::SUCCESS;
        }

        $outcome = $this->mailer->send($items);
        $this->cleanup($today);

        switch ($outcome->result) {
            case NotificationResultEnum::NotConfigured:
                $this->runRepository->finish($today, $slot, NotificationResultEnum::NotConfigured, 0, null);
                $io->warning(sprintf('%s が未設定のためメールを送りませんでした', implode('・', $outcome->missingSettings)));

                return Command::SUCCESS;
            case NotificationResultEnum::Failed:
                $this->runRepository->finish($today, $slot, NotificationResultEnum::Failed, 0, $outcome->errorSummary);
                $io->error(sprintf('メールの送信に失敗しました: %s', $outcome->errorSummary));

                return Command::FAILURE;
            default:
                $this->runRepository->finish($today, $slot, NotificationResultEnum::Sent, count($items), null);
                $io->writeln(sprintf('%s：%d件を送りました（宛先 %d）', $label, count($items), count($this->mailer->recipients())));

                return Command::SUCCESS;
        }
    }

    private function dryRun(SymfonyStyle $io, \DateTimeImmutable $today, string $label): int
    {
        $items = $this->collector->collect($today);
        if ($items === []) {
            $io->writeln(sprintf('%s：通常運航以外の便はありません', $label));

            return Command::SUCCESS;
        }

        $io->writeln('件名: ' . $this->mailer->subject(count($items)));
        $io->newLine();
        $io->write($this->mailer->body($items));

        return Command::SUCCESS;
    }

    private function cleanup(\DateTimeImmutable $today): void
    {
        $this->runRepository->deleteOlderThan($today->modify(sprintf('-%d days', self::RETENTION_DAYS)));
    }
}
