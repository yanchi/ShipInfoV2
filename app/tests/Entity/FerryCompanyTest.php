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

    public function testValuesAreTrimmed(): void
    {
        $company = (new FerryCompany())->setShipNames([' フェリー波之上 ', 'フェリーあけぼの']);

        $this->assertSame(['フェリー波之上', 'フェリーあけぼの'], $company->getShipNames());
    }

    /** setter は掃除して空なら NULL で持つ（data-model.md） */
    public function testBlankOnlyListIsStoredAsNull(): void
    {
        $company = (new FerryCompany())->setShipNames(['', ' '])->setAliases(['']);

        $ref = new \ReflectionClass($company);
        $this->assertNull($ref->getProperty('shipNames')->getValue($company));
        $this->assertNull($ref->getProperty('aliases')->getValue($company));
    }

    /** マイグレーションや手の SQL で文字列以外の要素が入っても落ちない */
    public function testNonStringElementsAreIgnored(): void
    {
        $company = new FerryCompany();
        (new \ReflectionClass($company))->getProperty('shipNames')->setValue($company, ['船A', null, 1, ['x']]);

        $this->assertSame(['船A'], $company->getShipNames());
    }

    public function testSettingEmptyArrayClearsValues(): void
    {
        $company = (new FerryCompany())->setShipNames(['船A'])->setAliases(['別名A']);

        $company->setShipNames([])->setAliases([]);

        $this->assertSame([], $company->getShipNames());
        $this->assertSame([], $company->getAliases());
    }
}
