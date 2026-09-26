"""Arithmetic regressions; fixtures here are never benchmark observations."""
import importlib.util
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("capacity_accounting", ROOT / "artifact/scripts/capacity_accounting.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def row(N=1024, ell=8192, alpha=4, rho=8):
    return mod.account(N=N, ell_bits=ell, alpha=alpha, rho0=rho,
                       w=alpha*rho, n=4096, q=mod.Q, C_bytes=131072)


class BufferAccountingTests(unittest.TestCase):
    def test_small_regression(self):
        d = row(N=256, ell=256, alpha=2)
        self.assertEqual((d["raw_db_bytes"], d["packed_query_bytes"], d["repeated_query_bytes"]),
                         (8*1024, 32*(1 << 20), 64*(1 << 20)))
        self.assertEqual((d["packed_reply_bytes"], d["repeated_reply_bytes"]), (128*1024, 256*1024))
        self.assertEqual(d["packed_query_to_raw_db_ratio"], "4096")

    def test_large_regression(self):
        d = row(N=16384, ell=2048, alpha=2)
        self.assertEqual((d["raw_db_bytes"], d["packed_query_bytes"], d["repeated_query_bytes"]),
                         (4*(1 << 20), 2*(1 << 30), 4*(1 << 30)))
        self.assertEqual((d["packed_reply_bytes"], d["repeated_reply_bytes"]), (128*1024, 256*1024))
        self.assertEqual(d["packed_query_to_raw_db_ratio"], "512")

    def test_16384_bit_query_raw_ratio(self):
        for N in (8, 1024, 16384):
            self.assertEqual(row(N=N, ell=16384)["packed_query_to_raw_db_ratio"], "64")

    def test_full_download_not_multiplied_by_alpha(self):
        self.assertEqual(row(alpha=2)["raw_db_bytes"], row(alpha=4)["raw_db_bytes"])

    def test_non_byte_aligned_raw_layouts(self):
        d = row(N=7, ell=257)
        self.assertEqual(d["raw_db_bit_packed_bytes"], 225)
        self.assertEqual(d["raw_db_per_record_byte_padded_bytes"], 231)
        self.assertEqual(d["raw_db_bit_packing_padding_bits"], 1)
        self.assertEqual(d["raw_db_per_record_padding_bits"], 49)
        self.assertNotEqual(d["packed_query_to_raw_db_ratio"], d["packed_query_to_per_record_padded_db_ratio"])

    def test_exact_fraction_not_float_rounding(self):
        d = row(ell=32769)
        self.assertEqual(Fraction(d["u"]), Fraction(4097, 1024))
        self.assertEqual(Fraction(d["packed_query_to_raw_db_ratio"]), Fraction(1048576, 32769))

    def test_two_block_reply_count(self):
        d = row(ell=65536)
        self.assertEqual((d["J"], d["L"], d["u"]), (8192, 2, "8"))
        self.assertEqual((d["packed_reply_ciphertexts"], d["repeated_reply_ciphertexts"]), (2, 8))
        self.assertEqual((d["packed_reply_bytes"], d["repeated_reply_bytes"]), (262144, 1048576))


class FixedSegmentCapacityTests(unittest.TestCase):
    def test_capacity_matrix(self):
        for ell, J, u, L, fits in ((4096, 512, "1/2", 1, True),
                                   (8192, 1024, "1", 1, True),
                                   (12288, 1536, "3/2", 1, False),
                                   (16384, 2048, "2", 1, False),
                                   (65536, 8192, "8", 2, False)):
            with self.subTest(ell=ell):
                d = row(ell=ell)
                self.assertEqual((d["J"], d["u"], d["L"], d["position_single_polynomial_fits"]), (J, u, L, fits))

    def test_coefficient_slot_boundary_and_order(self):
        records = [[r]*1024 for r in (1, 2, 3, 4)]
        packed = mod.position_pack_fixed_segments(records, 4096)
        for r, record in enumerate(records):
            self.assertEqual(packed[r*1024:(r+1)*1024], record)
        reversed_packed = mod.position_pack_fixed_segments(list(reversed(records)), 4096)
        self.assertEqual(reversed_packed[:1024], records[-1])

    def test_overfull_single_polynomial_rejected(self):
        with self.assertRaisesRegex(ValueError, "do not fit"):
            mod.position_pack_fixed_segments([[1]*1025]*4, 4096)

    def test_padding_does_not_claim_additional_blocks(self):
        packed = mod.position_pack_fixed_segments([[1, 2], [3, 4]], 8)
        self.assertEqual(packed, [1, 2, 3, 4, 0, 0, 0, 0])
        self.assertEqual(len(packed), 8)

    def test_record_boundary_differs_from_total_slot_boundary(self):
        before, at, after = [mod.layout(ell, 8, 4096, 4) for ell in (32767, 32768, 32769)]
        self.assertEqual((before["J"], before["L"], before["last_segment_valid_bits"]), (4096, 1, 7))
        self.assertEqual((at["J"], at["L"], at["u"]), (4096, 1, "4"))
        self.assertEqual((after["J"], after["L"], after["block_valid_coefficients"]), (4097, 2, [4096, 1]))
        self.assertEqual((after["padding_coefficients"], after["last_segment_valid_bits"]), (4095, 1))


class SufficientScreenTests(unittest.TestCase):
    def test_small_case_brute_force_against_threshold(self):
        # Enumerate an independent toy sufficient screen, without floor division.
        for q in (257, 4097, 65537):
            s = mod.no_wrap_screen(N=2, ell_bits=6, alpha=2, rho0=2, w=4, n=4, q=q)
            passing = [h for h in range(200) if 2*(15 + 288*h) < q]
            self.assertEqual(int(s["h_max"]), max(passing))

    def test_all_new_points_strict_integer_boundaries(self):
        for N, lengths in ((1024, mod.P5_LENGTHS), (8, mod.FUNCTIONAL_LENGTHS)):
            for ell in lengths:
                with self.subTest(N=N, ell=ell):
                    s = mod.no_wrap_screen(N=N, ell_bits=ell, alpha=4, rho0=8, w=32, n=4096, q=mod.Q)
                    h = int(s["h_max"])
                    for b in s["blocks"]:
                        A, D, hj = int(s["A"]), int(b["D_j"]), int(b["h_max_j"])
                        self.assertLess(2*(A+D*hj), mod.Q)
                        self.assertGreaterEqual(2*(A+D*(hj+1)), mod.Q)
                        self.assertLess(2*(A+D*h), mod.Q)
                    self.assertTrue(any(b["global_h_max_plus_1_fails_block"] for b in s["blocks"]))

    def test_partial_last_block_is_not_a_limiting_full_block(self):
        s = mod.no_wrap_screen(N=8, ell_bits=32769, alpha=4, rho0=8, w=32, n=4096, q=mod.Q)
        self.assertEqual(s["limiting_blocks"], [1])
        self.assertGreater(int(s["blocks"][1]["h_max_j"]), int(s["blocks"][0]["h_max_j"]))
        self.assertFalse(s["blocks"][1]["global_h_max_plus_1_fails_block"])

    def test_no_passing_h_is_not_impossibility(self):
        s = mod.no_wrap_screen(N=1, ell_bits=2, alpha=1, rho0=2, w=2, n=4, q=5)
        self.assertEqual(s["status"], "NO_NONNEGATIVE_H_PASSES_SUFFICIENT_SCREEN")
        self.assertIsNone(s["h_max"])
        self.assertTrue(s["not_an_impossibility_result"])

    def test_capacity_and_target_preconditions(self):
        with self.assertRaisesRegex(ValueError, "radix capacity"):
            mod.no_wrap_screen(N=8, ell_bits=8, alpha=4, rho0=8, w=31, n=4096, q=mod.Q)
        with self.assertRaisesRegex(ValueError, "ordered distinct"):
            mod.no_wrap_screen(N=3, ell_bits=8, alpha=4, rho0=8, w=32, n=4096, q=mod.Q)


class InputProvenanceTests(unittest.TestCase):
    def test_pins_and_grid_cardinality(self):
        rows, screens, verified = mod.build_rows(ROOT)
        self.assertEqual(len(rows), 68)
        self.assertEqual(len(screens), 8)
        self.assertEqual(sum(len(s["blocks"]) for s in screens), 10)
        self.assertEqual(sum(row["study"] == "B1" for row in rows), 48)
        self.assertEqual(sum(row["study"] == "B2-B" for row in rows), 12)
        self.assertTrue(all(item["sidecar_matches"] for item in verified))
        self.assertTrue(all(row["transport_measurement_status"] == "NOT_MEASURED" for row in rows))


if __name__ == "__main__":
    unittest.main()
