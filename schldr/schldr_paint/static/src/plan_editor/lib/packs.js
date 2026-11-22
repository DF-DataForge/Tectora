/** @odoo-module **/

/**
 * Which pots to buy for a quantity of paint: the mirror of lib/packs.py. See
 * there for the reasoning. No Odoo import.
 */

const SCALE = 1000;
const MAX_CELLS = 20000;

function gcd(a, b) {
    while (b) {
        [a, b] = [b, a % b];
    }
    return a;
}

/** [[volume, count]], largest first, for `need` out of `sizes`: volumes or
 *  [volume, price] pairs. */
export function choosePacks(need, sizes) {
    const byVolume = new Map();
    let all = [];
    for (const size of sizes) {
        const [volume, price] = Array.isArray(size) ? size : [size, 0];
        if (volume && volume > 0) {
            all.push([Number(volume), Number(price || 0)]);
        }
    }
    if (need <= 1e-9 || !all.length) {
        return [];
    }
    const priced = all.every(([, price]) => price > 0);
    for (const [volume, price] of all) {
        byVolume.set(volume, price);
    }
    all = [...byVolume.entries()].sort((a, b) => a[0] - b[0]);
    let units = all.map(([volume]) => Math.round(volume * SCALE));
    const weights = all.map(([volume, price]) => (priced ? price : volume ** 0.7));
    const step = units.reduce(gcd);
    units = units.map((unit) => unit / step);
    let target = Math.ceil((need * SCALE) / step - 1e-9);

    const counts = all.map(() => 0);
    const largest = Math.max(...units);
    if (target + largest > MAX_CELLS) {
        let best = 0;
        for (let index = 1; index < all.length; index++) {
            const current = weights[index] / units[index];
            const leading = weights[best] / units[best];
            if (current < leading || (current === leading && units[index] > units[best])) {
                best = index;
            }
        }
        const bulk = Math.floor((target - Math.floor(MAX_CELLS / 2)) / units[best]);
        counts[best] += bulk;
        target -= bulk * units[best];
    }

    const limit = target + largest;
    const cost = new Array(limit + 1).fill(Infinity);
    const pots = new Array(limit + 1).fill(0);
    const last = new Array(limit + 1).fill(-1);
    cost[0] = 0;
    for (let volume = 1; volume <= limit; volume++) {
        for (let index = 0; index < units.length; index++) {
            const unit = units[index];
            if (unit > volume || cost[volume - unit] === Infinity) {
                continue;
            }
            const candidate = cost[volume - unit] + weights[index];
            const number = pots[volume - unit] + 1;
            if (
                candidate < cost[volume] - 1e-9 ||
                (Math.abs(candidate - cost[volume]) <= 1e-9 && number < pots[volume])
            ) {
                cost[volume] = candidate;
                pots[volume] = number;
                last[volume] = index;
            }
        }
    }
    let bestVolume = -1;
    const key = (volume) => [Math.round(cost[volume] * 1e9) / 1e9, volume, pots[volume]];
    for (let volume = target; volume <= limit; volume++) {
        if (cost[volume] === Infinity) {
            continue;
        }
        if (bestVolume < 0) {
            bestVolume = volume;
            continue;
        }
        const [a, b] = [key(volume), key(bestVolume)];
        if (a[0] < b[0] || (a[0] === b[0] && (a[1] < b[1] || (a[1] === b[1] && a[2] < b[2])))) {
            bestVolume = volume;
        }
    }
    let volume = bestVolume;
    while (volume > 0) {
        const index = last[volume];
        counts[index] += 1;
        volume -= units[index];
    }
    const result = [];
    for (let index = all.length - 1; index >= 0; index--) {
        if (counts[index]) {
            result.push([all[index][0], counts[index]]);
        }
    }
    return result;
}

export function packedVolume(chosen) {
    return chosen.reduce((total, [volume, count]) => total + volume * count, 0);
}

export function describe(chosen, unit = "L") {
    return chosen
        .map(([volume, count]) => `${count} x ${String(volume).replace(".", ",")} ${unit}`)
        .join(" + ");
}
