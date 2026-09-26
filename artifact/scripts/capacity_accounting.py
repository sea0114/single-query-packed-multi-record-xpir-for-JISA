#!/usr/bin/env python3
"""Exact M2/M4/M5 accounting, without native execution or noise selection.

Run from any directory: python -B artifact/scripts/capacity_accounting.py
All input manifests are read-only and hash pinned. Outputs are derived arithmetic,
not timings, wire measurements, a second PIR protocol, or a security certificate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from fractions import Fraction
from math import gcd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    "revision_notes/B0_benchmark_manifest.json":
        "69c130a37990ce1262292476b29f6b365974ecdbe383df0511b66822f5e3bd6e",
    "revision_notes/B2_B_freeze_manifest.json":
        "b92848c888bd7f74113e0182bade7b4aed5e4e1d83960941170d7c2e25593e71",
}
REPRESENTATION = "XPIR-Q2-a-concat-b-RNS-major-uint64-little-endian"
Q = 5316911983137472318178862960259203073
P5_LENGTHS = (4096, 8192, 12288, 16384, 65536)
FUNCTIONAL_LENGTHS = (32767, 32768, 32769)


def ceil_div(a: int, b: int) -> int:
    if a < 0 or b <= 0:
        raise ValueError("ceil_div requires a >= 0 and b > 0")
    return (a + b - 1) // b


def positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def layout(ell_bits: int, rho0: int, n: int, alpha: int) -> dict:
    for name, value in (("ell_bits", ell_bits), ("rho0", rho0),
                        ("n", n), ("alpha", alpha)):
        positive_int(name, value)
    J = ceil_div(ell_bits, rho0)
    L = ceil_div(J, n)
    blocks = [min(n, J - j * n) for j in range(L)]
    return {
        "J": J, "L": L, "u": str(Fraction(alpha * J, n)),
        "block_valid_coefficients": blocks,
        "padding_coefficients": L * n - J,
        "last_segment_valid_bits": ell_bits - (J - 1) * rho0,
        "position_single_polynomial_fits": alpha * J <= n,
        "position_slot_polynomials_lower_bound": ceil_div(alpha * J, n),
    }


def position_pack_fixed_segments(records: list[list[int]], n: int) -> list[int]:
    """An integer slot layout used only to test the analytical capacity boundary.

    This is not encryption, ReplyGen, nor an executable comparator PIR scheme.
    It refuses overflow instead of reducing exponents modulo X^n+1.
    """
    positive_int("n", n)
    if not records or not records[0]:
        raise ValueError("nonempty records required")
    J = len(records[0])
    if any(len(record) != J for record in records):
        raise ValueError("fixed segment count required")
    if len(records) * J > n:
        raise ValueError("fixed segments do not fit one polynomial")
    return [coefficient for record in records for coefficient in record] + [0] * (n - len(records) * J)


def no_wrap_screen(*, N: int, ell_bits: int, alpha: int, rho0: int,
                   w: int, n: int, q: int) -> dict:
    """Check the published sufficient screen using integers exclusively.

    For odd q, A + D*h < q/2 iff A + D*h <= (q-1)//2.
    A passing screen is correctness-admissible under its formal good event;
    it neither selects r nor transfers the ideal law to the native sampler.
    """
    for name, value in (("N", N), ("w", w), ("q", q)):
        positive_int(name, value)
    if alpha > N:
        raise ValueError("ordered distinct targets require alpha <= N")
    info = layout(ell_bits, rho0, n, alpha)
    B, t = 1 << rho0, 1 << w
    if q % 2 != 1 or q <= t or gcd(t, q) != 1:
        raise ValueError("the declared screen requires odd q > t and gcd(t,q)=1")
    if t < B ** alpha:
        raise ValueError("radix capacity requires w >= alpha*rho0")
    A, half_q_floor = B ** alpha - 1, (q - 1) // 2
    C = half_q_floor - A
    if C < 0:
        return {
            "status": "NO_NONNEGATIVE_H_PASSES_SUFFICIENT_SCREEN",
            "A": str(A), "C": str(C), "h_max": None,
            "not_an_impossibility_result": True, "blocks": [],
        }
    block_rows = []
    for j, m in enumerate(info["block_valid_coefficients"], start=1):
        D = t * N * m * (B - 1)
        h = C // D
        at_h, at_next = A + D * h, A + D * (h + 1)
        assert 2 * at_h < q <= 2 * at_next
        block_rows.append({
            "block_j": j, "m_j": m, "D_j": str(D), "h_max_j": str(h),
            "A_plus_Dj_hmax_j": str(at_h),
            "A_plus_Dj_next": str(at_next),
            "h_max_j_passes_strict_screen": 2 * at_h < q,
            "h_max_j_plus_1_fails_strict_screen": 2 * at_next >= q,
            "integer_slack_at_h_max_j": str(half_q_floor - at_h),
        })
    hmax = min(int(row["h_max_j"]) for row in block_rows)
    limiting = [row["block_j"] for row in block_rows if int(row["h_max_j"]) == hmax]
    for row in block_rows:
        D = int(row["D_j"])
        row["global_h_max_passes_block"] = 2 * (A + D * hmax) < q
        row["global_h_max_plus_1_fails_block"] = 2 * (A + D * (hmax + 1)) >= q
    assert all(row["global_h_max_passes_block"] for row in block_rows)
    assert any(row["global_h_max_plus_1_fails_block"] for row in block_rows)
    return {
        "status": "PASS_FORMAL_SUFFICIENT_SCREEN_BOUNDARIES",
        "A": str(A), "C": str(C), "half_q_floor": str(half_q_floor),
        "h_max": str(hmax), "limiting_blocks": limiting, "blocks": block_rows,
        "r_selected": False, "native_failure_rate_certified": False,
        "concrete_security_certified": False,
    }


def account(*, N: int, ell_bits: int, alpha: int, rho0: int, w: int,
            n: int, q: int, C_bytes: int) -> dict:
    for name, value in (("N", N), ("C_bytes", C_bytes)):
        positive_int(name, value)
    if alpha > N:
        raise ValueError("alpha must not exceed N")
    info = layout(ell_bits, rho0, n, alpha)
    # A full download contains the database once, regardless of alpha.
    raw_bit_packed = ceil_div(N * ell_bits, 8)
    raw_per_record_padded = N * ceil_div(ell_bits, 8)
    return {
        "N": N, "ell_bits": ell_bits, "alpha": alpha, "rho0": rho0,
        "n": n, "q_id": "Q2", "q": str(q), "w": w,
        "J": info["J"], "L": info["L"], "u": info["u"],
        "block_valid_coefficients": ";".join(map(str, info["block_valid_coefficients"])),
        "padding_coefficients": info["padding_coefficients"],
        "last_segment_valid_bits": info["last_segment_valid_bits"],
        "position_single_polynomial_fits": info["position_single_polynomial_fits"],
        "position_slot_polynomials_lower_bound": info["position_slot_polynomials_lower_bound"],
        "ciphertext_representation_id": REPRESENTATION, "C_bytes": C_bytes,
        "raw_size_basis": "GLOBAL_BIT_PACKING_WITH_FINAL_BYTE_PADDING",
        "raw_db_bytes": raw_bit_packed,
        "raw_db_bit_packed_bytes": raw_bit_packed,
        "raw_db_per_record_byte_padded_bytes": raw_per_record_padded,
        "raw_db_bit_packing_padding_bits": 8 * raw_bit_packed - N * ell_bits,
        "raw_db_per_record_padding_bits": 8 * raw_per_record_padded - N * ell_bits,
        "packed_query_ciphertexts": N,
        "repeated_query_ciphertexts": alpha * N,
        "packed_reply_ciphertexts": info["L"],
        "repeated_reply_ciphertexts": alpha * info["L"],
        "packed_query_bytes": N * C_bytes,
        "repeated_query_bytes": alpha * N * C_bytes,
        "packed_reply_bytes": info["L"] * C_bytes,
        "repeated_reply_bytes": alpha * info["L"] * C_bytes,
        "packed_query_to_raw_db_ratio": str(Fraction(N * C_bytes, raw_bit_packed)),
        "packed_query_to_per_record_padded_db_ratio": str(Fraction(N * C_bytes, raw_per_record_padded)),
        "transport_measurement_status": "NOT_MEASURED",
    }


def verified_inputs(root: Path) -> tuple[dict, dict, list[dict]]:
    manifests, verified = [], []
    for relpath, pinned_hash in PINS.items():
        path = root / relpath
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != pinned_hash:
            raise ValueError(f"input hash mismatch: {relpath}")
        sidecar = path.with_suffix(".json.sha256").read_text(encoding="utf-8-sig").split()[0]
        if sidecar != actual_hash:
            raise ValueError(f"input sidecar mismatch: {relpath}")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        crypto = data["crypto"]
        if int(crypto["q"]) != Q or crypto["n"] != 4096:
            raise ValueError("n/q differs from declared Q2")
        if int(crypto["primes"][0]) * int(crypto["primes"][1]) != Q:
            raise ValueError("Q2 product mismatch")
        if crypto["recursion_dimension"] != 1 or crypto["aggregation_factor"] != 1:
            raise ValueError("input is not the declared flat native path")
        C_bytes = data["payload"]["ciphertext_bytes"]
        if C_bytes != 2 * crypto["n"] * len(crypto["primes"]) * 8:
            raise ValueError("native a||b/RNS/uint64 buffer size mismatch")
        manifests.append(data)
        verified.append({"path": relpath, "sha256": actual_hash, "sidecar_matches": True})
    return manifests[0], manifests[1], verified


def build_rows(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    b0, b2b, verified = verified_inputs(root)
    rows, screens = [], []
    for study, manifest, source in (("B1", b0, next(iter(PINS))),
                                     ("B2-B", b2b, list(PINS)[1])):
        for workload in manifest["workloads"]:
            params = dict(N=workload["N"], ell_bits=workload["ell_bits"],
                          alpha=workload.get("alpha", 2), rho0=workload["rho_0"],
                          w=workload["w"], n=manifest["crypto"]["n"],
                          q=int(manifest["crypto"]["q"]),
                          C_bytes=manifest["payload"]["ciphertext_bytes"])
            row = account(**params)
            if (row["J"], row["L"]) != (workload["J"], workload["L"]):
                raise ValueError("historical J/L mismatch")
            rows.append({"study": study, "purpose": "HISTORICAL_PROFILE_ACCOUNTING",
                         "evidence_status": "DERIVED_ARITHMETIC_NOT_NEW_MEASUREMENT",
                         "source_manifest": source,
                         "source_workload_id": workload.get("id", workload.get("point_id")),
                         "views": "COLD;ONLINE", **row})
    if len(b0["workloads"]) != 48 or len(b2b["workloads"]) != 12:
        raise ValueError("historical grid cardinality mismatch")
    for purpose, N, lengths in (("P5_PLANNED_CAPACITY", 1024, P5_LENGTHS),
                                ("FUNCTIONAL_BOUNDARY_ARITHMETIC", 8, FUNCTIONAL_LENGTHS)):
        for ell in lengths:
            params = dict(N=N, ell_bits=ell, alpha=4, rho0=8, w=32,
                          n=b0["crypto"]["n"], q=int(b0["crypto"]["q"]),
                          C_bytes=b0["payload"]["ciphertext_bytes"])
            row = account(**params)
            identity = {"study": "B3_PROPOSED", "purpose": purpose,
                        "evidence_status": "ANALYTICAL_ONLY_NATIVE_EXECUTION_NOT_ASSERTED",
                        "source_manifest": "B0/B2-B representation + M1-M7 plan v1.0",
                        "source_workload_id": f"A4_N{N}_ell{ell}",
                        "views": "COLD;ONLINE" if purpose == "P5_PLANNED_CAPACITY" else "NOT_A_PERFORMANCE_POINT"}
            rows.append({**identity, **row})
            screen_params = {key: value for key, value in params.items() if key != "C_bytes"}
            screens.append({**identity, **{key: row[key] for key in
                           ("N", "ell_bits", "alpha", "rho0", "w", "n", "q", "J", "L", "u")},
                            **no_wrap_screen(**screen_params)})
    return rows, screens, verified


def render_table(rows: list[dict]) -> str:
    selected = [next(row for row in rows if row["study"] == "B1" and
                     row["N"] == N and row["ell_bits"] == ell and row["rho0"] == 8)
                for N, ell in ((256, 256), (16384, 2048))]
    selected += [row for row in rows if row["purpose"] == "P5_PLANNED_CAPACITY"]
    lines = [
        "% Generated by artifact/scripts/capacity_accounting.py; arithmetic only.",
        r"\begin{table}[t]", r"\centering", r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\caption{Raw database and uncompressed native ciphertext buffers. All rows use",
        r"$n=4096$, $\rho_0=8$, $w=8\alpha$, and $C_{\rm bytes}=131072$.",
        r"P/R denotes packed/repeated; H denotes historical workloads and A denotes",
        r"analytical capacity examples. A rows do not assert measured performance.",
        r"Sizes are binary units; each raw database is counted once.}",
        r"\label{tab:flat-buffer-accounting}",
        r"\begin{tabular}{@{}clrrrr@{}}", r"\hline",
        r" & $(N,\ell,\alpha,L)$ & Raw & Query P/R & Reply P/R & $Q_{\rm P}/D$\\",
        r" & (bits for $\ell$) & (KiB) & (MiB) & (KiB) & \\", r"\hline",
    ]
    for index, row in enumerate(selected):
        group = "H" if index < 2 else "A"
        values = (group, f"$({row['N']},{row['ell_bits']},{row['alpha']},{row['L']})$",
                  str(Fraction(row["raw_db_bytes"], 1024)),
                  f"{Fraction(row['packed_query_bytes'], 1 << 20)}/{Fraction(row['repeated_query_bytes'], 1 << 20)}",
                  f"{Fraction(row['packed_reply_bytes'], 1024)}/{Fraction(row['repeated_reply_bytes'], 1024)}",
                  row["packed_query_to_raw_db_ratio"])
        lines.append(" & ".join(values) + r"\\")
    lines += [r"\hline", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    rows, screens, inputs = build_rows(root)
    out = root / "artifact/results/accounting"
    generated = root / "artifact/generated"
    out.mkdir(parents=True, exist_ok=True)
    generated.mkdir(parents=True, exist_ok=True)
    with (out / "full_grid.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "status": "PASS_EXACT_ARITHMETIC_ONLY",
        "source_inputs": inputs,
        "representation_id": REPRESENTATION,
        "ciphertext_bytes": rows[0]["C_bytes"],
        "historical_workload_rows": 60, "historical_view_cells_covered": 120,
        "planned_capacity_rows": 5, "functional_boundary_rows": 3,
        "hmax_screen_rows": len(screens),
        "all_block_hmax_boundaries_pass": all(
            block["h_max_j_passes_strict_screen"] and block["h_max_j_plus_1_fails_strict_screen"]
            for screen in screens for block in screen["blocks"]),
        "new_native_observations": 0, "noise_r_selected": False,
        "security_or_native_reliability_certificate": False,
        "raw_db_definition": "ceil(N*ell/8) bytes after global bit packing; also report N*ceil(ell/8) per-record-byte-padded bytes. Both coincide for byte-aligned lengths.",
        "view_semantics": "Each historical workload row covers both COLD and ONLINE; buffer accounting does not depend on the timing view.",
        "multi_block_status": "ell=65536 is an analytical row; its inclusion as a performance point is decided in the separate frozen B3 protocol before formal measurements.",
        "position_capacity_scope": "Fixed J-segment encoding, direct disjoint coefficient positions in one polynomial. ceil(alpha*J/n) is a slot-space lower bound, not an implemented PIR reply count.",
        "screens": screens,
    }
    (out / "correctness_screens.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (generated / "payload_table.tex").write_text(render_table(rows), encoding="utf-8")
    (out / "README.md").write_text(
        "# Exact capacity and native-buffer accounting\n\n"
        "Recompute with `python -B artifact/scripts/capacity_accounting.py`; no external packages or benchmark host are needed. "
        "Run `python -B -m unittest discover -s artifact/tests -p test_capacity_accounting.py -v` for the arithmetic regressions.\n\n"
        "`full_grid.csv` has 48 historical B1, 12 historical B2-B, five proposed P5, and three small-N functional-boundary rows. "
        "Historical rows apply to both views (96 B1 and 24 B2-B cells); proposed rows are arithmetic and do not assert completed experiments. "
        "The 65536-bit example is included analytically regardless of whether the separate B3 protocol enables that optional measurement.\n\n"
        "`raw_db_bytes` uses ceil(N*ell/8): the records are concatenated as bits and only the final byte is padded. "
        "The separate per-record-padded column is N*ceil(ell/8). No fractional bytes are reported. "
        "A full download counts the database once, not alpha times. Ratios and u are exact rational strings. "
        "The uncompressed native representation is two components, two RNS residues, n uint64 values each: 2*2*4096*8=131072 bytes. "
        "These are local buffers, not measured wire traffic, and omit network framing or compression.\n\n"
        "`correctness_screens.json` checks every new block's exact h_max,j and h_max,j+1 using the strict integer no-wrap inequality. "
        "It also checks the minimum global h_max on all blocks and identifies limiting blocks. "
        "No r is chosen; B_err is not treated as an absolute coefficient bound. "
        "This provides no native error probability, sampler bridge, or cryptographic security estimate.\n\n"
        "The position-packing tests model only fixed segments in disjoint coefficient slots. "
        "u=alpha*J/n=1 and J=n are distinct boundaries. A slot-space lower bound is not the reply count of a second PIR protocol. "
        "The script does not implement or benchmark such a protocol.\n",
        encoding="utf-8")
    output_names = ["artifact/results/accounting/full_grid.csv",
                    "artifact/results/accounting/correctness_screens.json",
                    "artifact/results/accounting/README.md", "artifact/generated/payload_table.tex"]
    output_hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in output_names}
    (out / "generation_manifest.json").write_text(json.dumps({
        "schema": "M1_M7_EXACT_ACCOUNTING_V1", "inputs": inputs,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outputs": output_hashes, "rows": len(rows), "new_native_observations": 0,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "rows": len(rows),
                      "screen_rows": len(screens),
                      "screen_blocks": sum(len(s["blocks"]) for s in screens),
                      "output_directory": str(out)}))


if __name__ == "__main__":
    main()
