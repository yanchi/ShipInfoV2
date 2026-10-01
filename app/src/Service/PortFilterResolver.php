<?php

namespace App\Service;

use App\Entity\Port;
use App\Enum\RouteDirectionEnum;
use App\View\PortFilter;
use App\View\PortFilterResolution;
use Symfony\Component\HttpFoundation\Cookie;
use Symfony\Component\HttpFoundation\Request;

/**
 * クエリ（port・dir）・フォーム（POST /ports/filter）・Cookie（port_filter）から絞り込み条件を作る
 * （specs/5-ui-readability/contracts/http-routes.md）。
 *
 * - 表示はクエリ優先。クエリが無ければ Cookie
 * - Cookie を書くのはフォームの「保存」、消すのはフォームの「保存を解除」と Cookie の値が不正なときだけ。
 *   保存・解除は POST で受け、CSRF トークンが正しいときだけ行う（リンクや他サイトから書き換えられないように）
 */
class PortFilterResolver
{
    public const COOKIE_NAME = 'port_filter';

    public const ACTION_SHOW  = 'show';
    public const ACTION_SAVE  = 'save';
    public const ACTION_CLEAR = 'clear';

    private const PATH = '/ports';

    /**
     * GET /ports。Cookie は読むだけで、書くのは不正な値を消すときだけ。
     *
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     */
    public function resolve(Request $request, array $boardStops): PortFilterResolution
    {
        $validPortIds = $this->validPortIds($boardStops);
        [$saved, $cookieInvalid] = $this->readCookie($request, $validPortIds);
        $clearCookie = $cookieInvalid ? $this->clearCookie() : null;

        if (!$request->query->has('port') && !$request->query->has('dir')) {
            return new PortFilterResolution($saved ?? PortFilter::none(), null, $clearCookie);
        }

        $port = $this->parsePort((string) $request->query->get('port', ''), $validPortIds);
        $dir  = $this->parseDirection((string) $request->query->get('dir', ''));

        return new PortFilterResolution(new PortFilter($port['value'], $dir['value'], $saved !== null), null, $clearCookie);
    }

    /**
     * POST /ports/filter（絞り込みフォーム）。どの操作も GET /ports へリダイレクトする（PRG）。
     *
     * - show:  条件の URL へ。Cookie は変えない
     * - save:  値が正しくトークンも正しければ Cookie を書く。それ以外は書かずに条件の URL へ
     * - clear: トークンが正しければ Cookie を消す
     *
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     * @param bool $tokenValid CSRF トークンが正しいか（Controller で確かめる）
     */
    public function submit(Request $request, array $boardStops, bool $tokenValid): PortFilterResolution
    {
        $validPortIds = $this->validPortIds($boardStops);
        [, $cookieInvalid] = $this->readCookie($request, $validPortIds);
        $clearCookie = $cookieInvalid ? $this->clearCookie() : null;
        $action      = (string) $request->request->get('action', self::ACTION_SHOW);

        if ($action === self::ACTION_CLEAR) {
            return new PortFilterResolution(PortFilter::none(), self::PATH, $tokenValid ? $this->clearCookie() : $clearCookie);
        }

        $port   = $this->parsePort((string) $request->request->get('port', ''), $validPortIds);
        $dir    = $this->parseDirection((string) $request->request->get('dir', ''));
        $filter = new PortFilter($port['value'], $dir['value']);

        if ($action !== self::ACTION_SAVE || !$tokenValid || !$port['valid'] || !$dir['valid']) {
            // 表示だけ、またはトークン・値が不正なら保存しない（もとの Cookie は残す）
            return new PortFilterResolution($filter, $this->url($filter), $clearCookie);
        }
        if (!$filter->isActive()) {
            // 「全港・両方向」を保存する = 保存した条件を消す
            return new PortFilterResolution($filter, self::PATH, $this->clearCookie());
        }

        return new PortFilterResolution($filter, $this->url($filter), $this->writeCookie($filter));
    }

    /**
     * トップ用。クエリは見ず Cookie だけを読む（リダイレクトしない）。
     *
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     */
    public function resolveFromCookie(Request $request, array $boardStops): PortFilterResolution
    {
        [$saved, $cookieInvalid] = $this->readCookie($request, $this->validPortIds($boardStops));

        return new PortFilterResolution($saved ?? PortFilter::none(), null, $cookieInvalid ? $this->clearCookie() : null);
    }

    /**
     * 絞り込みの選択肢にする出発港（下りの寄港順 → 上りにしか無い港、重複なし）。
     *
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     * @return list<Port>
     */
    public function departurePorts(array $boardStops): array
    {
        $ports = [];
        foreach ($boardStops as $stops) {
            foreach ($stops['departurePorts'] as $port) {
                $ports[$port->getId()] ??= $port;
            }
        }

        return array_values($ports);
    }

    /**
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     * @return list<int>
     */
    private function validPortIds(array $boardStops): array
    {
        return array_map(static fn (Port $p) => $p->getId(), $this->departurePorts($boardStops));
    }

    /**
     * @param list<int> $validPortIds
     * @return array{0: ?PortFilter, 1: bool} [保存した条件（無い・不正なら null）, 不正か]
     */
    private function readCookie(Request $request, array $validPortIds): array
    {
        $raw = $request->cookies->get(self::COOKIE_NAME);
        if ($raw === null) {
            return [null, false];
        }

        parse_str((string) $raw, $values);
        $port = $this->parsePort(\is_string($values['port'] ?? null) ? $values['port'] : '', $validPortIds);
        $dir  = $this->parseDirection(\is_string($values['dir'] ?? null) ? $values['dir'] : '');
        if (!$port['valid'] || !$dir['valid'] || ($port['value'] === null && $dir['value'] === null)) {
            return [null, true];
        }

        return [new PortFilter($port['value'], $dir['value'], true), false];
    }

    /**
     * 空・all は全港（正しい値）。存在しない港は null 扱いで、不正な値とする。
     *
     * @param list<int> $validPortIds
     * @return array{value: ?int, valid: bool}
     */
    private function parsePort(string $value, array $validPortIds): array
    {
        if ($value === '' || $value === 'all') {
            return ['value' => null, 'valid' => true];
        }
        if (ctype_digit($value) && \in_array((int) $value, $validPortIds, true)) {
            return ['value' => (int) $value, 'valid' => true];
        }

        return ['value' => null, 'valid' => false];
    }

    /**
     * @return array{value: ?RouteDirectionEnum, valid: bool}
     */
    private function parseDirection(string $value): array
    {
        if ($value === '') {
            return ['value' => null, 'valid' => true];
        }
        $direction = RouteDirectionEnum::tryFrom($value);

        return ['value' => $direction, 'valid' => $direction !== null];
    }

    /**
     * 表示する GET の URL。条件が空なら、Cookie の条件で表示されないよう port=all を付ける。
     */
    private function url(PortFilter $filter): string
    {
        $query = $filter->toQuery() ?: ['port' => 'all'];

        return self::PATH . '?' . http_build_query($query);
    }

    private function writeCookie(PortFilter $filter): Cookie
    {
        return Cookie::create(
            self::COOKIE_NAME,
            http_build_query($filter->toQuery()),
            new \DateTimeImmutable('+1 year'),
            '/',
            null,
            null,
            true,
            false,
            Cookie::SAMESITE_LAX,
        );
    }

    private function clearCookie(): Cookie
    {
        return Cookie::create(self::COOKIE_NAME)->withExpires(1);
    }
}
