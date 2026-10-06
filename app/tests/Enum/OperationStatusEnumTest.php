<?php

namespace App\Tests\Enum;

use App\Enum\OperationStatusEnum;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class OperationStatusEnumTest extends TestCase
{
    /**
     * @return iterable<string, array{OperationStatusEnum, string, bool}>
     */
    public static function cases(): iterable
    {
        yield 'operating' => [OperationStatusEnum::Operating, '通常運航', false];
        yield 'delayed' => [OperationStatusEnum::Delayed, '条件付・遅延', true];
        yield 'skipped' => [OperationStatusEnum::Skipped, '抜港', true];
        yield 'cancelled' => [OperationStatusEnum::Cancelled, '欠航', true];
        yield 'suspended' => [OperationStatusEnum::Suspended, '運休', true];
        yield 'unknown' => [OperationStatusEnum::Unknown, '不明', true];
        yield 'no_service' => [OperationStatusEnum::NoService, '便なし', false];
    }

    #[DataProvider('cases')]
    public function testLabelAndIsIrregular(OperationStatusEnum $status, string $label, bool $irregular): void
    {
        $this->assertSame($label, $status->label());
        $this->assertSame($irregular, $status->isIrregular());
    }

    public function testIrregularCasesMatchIsIrregular(): void
    {
        $expected = array_values(array_filter(
            OperationStatusEnum::cases(),
            static fn (OperationStatusEnum $s): bool => $s->isIrregular(),
        ));

        $this->assertSame($expected, OperationStatusEnum::irregularCases());
        $this->assertCount(5, OperationStatusEnum::irregularCases());
    }
}
