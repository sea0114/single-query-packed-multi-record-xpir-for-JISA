#!/usr/bin/env python3
"""Frozen-design primitives; public fixture randomness is never crypto RNG.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import time

CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parents[1]
BACKEND_COMMIT = '75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c'
Q = 5316911983137472318178862960259203073
N = 4096
W = 24
EMAX = 398
MEMORY_LIMIT = 8 * 2**30
SEEDS = {'pilot_fixture': 2026100101, 'pilot_targets': 2026100102,
         'tuning_fixture': 2026100111, 'tuning_targets': 2026100112,
         'tuning_schedule': 2026100113, 'formal_fixture': 2026100121,
         'formal_targets': 2026100122, 'formal_schedule': 2026100123,
         'bootstrap': 2026100131}


def now():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, obj):
    path = Path(path).resolve()
    if not path.is_relative_to(CORE.resolve()):
        raise ValueError('new experiment outputs must stay under core_rebuild')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write('\n')


def normalize(obj):
    if isinstance(obj, list):
        return [normalize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, str):
        if obj in ('true', 'false'):
            return obj == 'true'
        if obj.isdecimal():
            return int(obj)
    return obj


def fixture_bytes(records, ell, seed, kind='random'):
    """One seeded public uniform-byte fixture, separated from native randomness."""
    rng = random.Random(seed)
    width = (ell + 7) // 8
    if kind == 'zero':
        data = bytearray(records * width)
    elif kind == 'max':
        data = bytearray(b'\xff' * (records * width))
    else:
        data = bytearray(rng.randbytes(records * width))
    if ell % 8:
        mask = (1 << (ell % 8)) - 1
        for i in range(records):
            data[(i + 1) * width - 1] &= mask
    if kind == 'equal':
        for i in range(1, records):
            data[i * width:(i + 1) * width] = data[:width]
    return bytes(data)


def targets(records, alpha, seed):
    return random.Random(seed).sample(range(records), alpha)


def config(kind, rho, concurrency, threads):
    return {'config_id': f'{kind}_rho{rho:02}_c{concurrency}_t{threads}',
            'kind': kind, 'rho_0': rho, 'concurrency': concurrency,
            'threads': threads, 'w': W, 'n': N}


def candidates(alpha, cpus=4, kind='P', rho=None):
    widths = [rho] if rho is not None else [r for r in (4, 6, 8, 12, 16, 24)
                                             if r * (alpha if kind == 'P' else 1) <= W]
    if kind == 'P':
        policies = [(1, 1), (1, cpus)]
    else:
        policies = [(c, t) for c in sorted({1, min(alpha, cpus)})
                    for t in sorted({1, cpus // c})]
    result = {config(kind, r, c, t)['config_id']: config(kind, r, c, t)
              for r in widths for c, t in policies if c * t <= cpus}
    return [result[k] for k in sorted(result)]


def main_workloads(tier='full'):
    ns = {'full': (256, 1024, 4096), 'compact': (256, 1024), 'minimal': (1024,)}[tier]
    return [{'workload_id': f'primary_N{n}_a{a}_ell{ell}', 'study': 'primary',
             'N': n, 'alpha': a, 'ell_bits': ell}
            for n, a, ell in itertools.product(ns, (2, 3, 4), (4096, 32768))]


def capacity_workloads():
    result = []
    for alpha, rho, lengths in [(2, 12, (49144, 49152, 49160, 98304)),
                                (4, 6, (24568, 24576, 24584, 49152))]:
        for ell in lengths:
            result.append({'workload_id': f'capacity_N1024_a{alpha}_ell{ell}',
                           'study': 'capacity', 'N': 1024, 'alpha': alpha,
                           'ell_bits': ell, 'packed_rho': rho})
    return result


def layout(ell, rho):
    j = (ell + rho - 1) // rho
    return {'J': j, 'L': (j + N - 1) // N}


def integer_screen(records, ell, alpha, rho):
    values = layout(ell, rho)
    a = (1 << (alpha * rho)) - 1
    blocks = []
    for j in range(values['L']):
        eta = min(N, values['J'] - j * N)
        lhs = 2 * (a + (1 << W) * records * eta * ((1 << rho) - 1) * EMAX)
        blocks.append({'block': j + 1, 'eta': eta, 'twice_bound': str(lhs),
                       'strict_no_wrap': lhs < Q})
    return dict(values, blocks=blocks, strict_no_wrap=all(x['strict_no_wrap'] for x in blocks))
