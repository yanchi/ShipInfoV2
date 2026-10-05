<?php

namespace App\Tests\Service;

use App\Service\NotificationSlotResolver;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class NotificationSlotResolverTest extends TestCase
{
    /**
     * @return iterable<string, array{string, int|null}>
     */
    public static function times(): iterable
    {
        yield '01:00' => ['2026-10-07 01:00:00', 1];
        yield '01:09:59' => ['2026-10-07 01:09:59', 1];
        yield '01:10:00' => ['2026-10-07 01:10:00', null];
        yield '00:59' => ['2026-10-07 00:59:00', null];
        yield '06:05' => ['2026-10-07 06:05:00', 6];
        yield '15:00' => ['2026-10-07 15:00:00', 15];
        yield '03:12' => ['2026-10-07 03:12:00', null];
    }

    #[DataProvider('times')]
    public function testResolve(string $now, ?int $expected): void
    {
        $this->assertSame($expected, (new NotificationSlotResolver())->resolve(new \DateTimeImmutable($now)));
    }

    public function testFromOptionAcceptsSlots(): void
    {
        $resolver = new NotificationSlotResolver();

        $this->assertSame(1, $resolver->fromOption('1'));
        $this->assertSame(6, $resolver->fromOption('6'));
        $this->assertSame(15, $resolver->fromOption('15'));
    }

    /**
     * @return iterable<string, array{string}>
     */
    public static function invalid(): iterable
    {
        yield 'zero' => ['0'];
        yield 'seven' => ['7'];
        yield 'text' => ['abc'];
        yield 'empty' => [''];
    }

    #[DataProvider('invalid')]
    public function testFromOptionRejectsOthers(string $value): void
    {
        $this->expectException(\InvalidArgumentException::class);

        (new NotificationSlotResolver())->fromOption($value);
    }
}
