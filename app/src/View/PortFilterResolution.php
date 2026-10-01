<?php

namespace App\View;

use Symfony\Component\HttpFoundation\Cookie;

/**
 * PortFilterResolver が Controller に返す指示。
 */
final readonly class PortFilterResolution
{
    public function __construct(
        public PortFilter $filter,
        /** リダイレクト先（save=1・clear=1 のとき） */
        public ?string $redirectTo = null,
        /** レスポンスに付ける Cookie（書く・消すとき）。変えないときは null */
        public ?Cookie $cookie = null,
    ) {
    }
}
