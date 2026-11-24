<?php

namespace App\Tests\Entity;

use App\Entity\FerryCompany;
use PHPUnit\Framework\TestCase;

/** 船の名前・別名（specs/19-search-query-wording/data-model.md） */
class FerryCompanyTest extends TestCase
{
    public function testShipNamesAndAliasesDefaultToEmpty(): void
    {
        $company = new FerryCompany();

        $this->assertSame([], $company->getShipNames());
        $this->assertSame([], $company->getAliases());
    }

    public function testGettersDropEmptyStrings(): void
    {
        $company = (new FerryCompany())
            ->setShipNames(['', 'フェリー波之上', '  ', 'フェリーあけぼの'])
            ->setAliases(['Aライン（エーライン）', '']);

        $this->assertSame(['フェリー波之上', 'フェリーあけぼの'], $company->getShipNames());
        $this->assertSame(['Aライン（エーライン）'], $company->getAliases());
    }

    public function testSettingEmptyArrayClearsValues(): void
    {
        $company = (new FerryCompany())->setShipNames(['船A'])->setAliases(['別名A']);

        $company->setShipNames([])->setAliases([]);

        $this->assertSame([], $company->getShipNames());
        $this->assertSame([], $company->getAliases());
    }
}
