<?php

namespace App\Service;

use App\Entity\Port;
use App\Enum\RouteDirectionEnum;
use App\View\PortFilter;
use App\View\PortFilterResolution;
use Symfony\Component\HttpFoundation\Cookie;
use Symfony\Component\HttpFoundation\Request;

/**
 * クエリ（port・dir・save・clear）と Cookie（port_filter）から絞り込み条件を作る
 * （specs/5-ui-readability/contracts/http-routes.md）。
 *
 * - 表示はクエリ優先。クエリが無ければ Cookie
 * - Cookie を書くのは save=1、消すのは clear=1 と Cookie の値が不正なときだけ
 */
class PortFilterResolver
{
    public const COOKIE_NAME = 'port_filter';

    private const PATH = '/ports';

    /**
     * @param list<array{direction: RouteDirectionEnum, departurePorts: list<Port>, arrivalPort: Port}> $boardStops
     */
    public function resolve(Request $request, array $boardStops): PortFilterResolution
    {
        $validPortIds = $this->validPortIds($boardStops);
        [$saved, $cookieInvalid] = $this->readCookie($request, $validPortIds);
        $clearCookie = $cookieInvalid ? $this->clearCookie() : null;

        if ($request->query->get('clear') === '1') {
            return new PortFilterResolution(PortFilter::none(), self::PATH, $this->clearCookie());
        }

        if (!$request->query->has('port') && !$request->query->has('dir')) {
            return new PortFilterResolution($saved ?? PortFilter::none(), null, $clearCookie);
        }

        $port = $this->parsePort((string) $request->query->get('port', ''), $validPortIds);
        $dir  = $this->parseDirection((string) $request->query->get('dir', ''));

        if ($request->query->get('save') !== '1') {
            return new PortFilterResolution(new PortFilter($port['value'], $dir['value'], $saved !== null), null, $clearCookie);
        }

        $filter = new PortFilter($port['value'], $dir['value']);
        if (!$port['valid'] || !$dir['valid']) {
            // 不正な値は保存しない（もとの Cookie は残す）。正しい値だけを残して表示する
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
     * save を除いた URL。条件が空なら、Cookie の条件で表示されないよう port=all を付ける。
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
