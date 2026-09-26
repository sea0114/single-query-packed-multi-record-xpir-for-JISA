"""Exact-integer reference model for S4-0 radix packing; NOT an XPIR implementation.

Run: python tests/test_m1_encoding.py -v
Bit order: increasing bit significance within each segment/field/byte.
Fixed seeds and toy parameters are for functionality, not cryptographic use.
"""
import itertools
import random
import unittest


def shape(ell, rho, n):
    if ell < 1 or rho < 1 or n < 1 or n & (n - 1):
        raise ValueError("invalid encoding parameters")
    j = (ell + rho - 1) // rho
    return j, (j + n - 1) // n


def encode(bits, rho, n):
    j, blocks = shape(len(bits), rho, n)
    if any(b not in (0, 1) for b in bits):
        raise ValueError("not a bit string")
    segments = [sum(b << v for v, b in enumerate(bits[h*rho:(h+1)*rho]))
                for h in range(j)]
    segments += [0] * (blocks*n - j)
    return [segments[h:h+n] for h in range(0, blocks*n, n)]


def decode(polys, ell, rho, n):
    j, blocks = shape(ell, rho, n)
    if len(polys) != blocks or any(len(p) != n for p in polys):
        raise ValueError("wrong polynomial shape")
    fields = list(itertools.chain.from_iterable(polys))
    if any(not 0 <= x < (1 << rho) for x in fields):
        raise ValueError("segment outside legal domain")
    if any(fields[j:]):
        raise ValueError("nonzero block padding")
    bits = [(x >> v) & 1 for x in fields[:j] for v in range(rho)]
    if any(bits[ell:]):
        raise ValueError("nonzero segment padding")
    return bits[:ell]


def radix_weights(rho, alpha):
    if rho < 1 or alpha < 1:
        raise ValueError("invalid radix parameters")
    return tuple(1 << (rho*r) for r in range(alpha))


def validate_weights(rho, w, weights):
    if tuple(weights) != radix_weights(rho, len(weights)):
        raise ValueError("weights must be derived radix powers")
    if w < rho * len(weights):
        raise ValueError("insufficient plaintext capacity")


def pack(values, rho, w, weights):
    validate_weights(rho, w, weights)
    if len(values) != len(weights) or any(not 0 <= x < (1 << rho) for x in values):
        raise ValueError("segment outside legal domain")
    return sum(k*x for k, x in zip(weights, values))


def unpack(y, rho, alpha, t):
    weights = radix_weights(rho, alpha)
    if t < (1 << (rho*alpha)):
        raise ValueError("insufficient plaintext capacity")
    if not 0 <= y < (1 << (rho*alpha)):
        raise ValueError("coefficient outside radix image")
    return tuple((y // k) % (1 << rho) for k in weights)


def serialize_fields(fields, w):
    """Reference serialization only; no claim of XPIR native compatibility."""
    if any(not 0 <= x < (1 << w) for x in fields):
        raise ValueError("field overflow")
    bits = [(x >> v) & 1 for x in fields for v in range(w)]
    bits += [0] * ((-len(bits)) % 8)
    return bytes(sum(bits[h+v] << v for v in range(8)) for h in range(0, len(bits), 8))


def import_fields(buf, count, w):
    logical_bits = count * w
    if len(buf) != (logical_bits + 7)//8:
        raise ValueError("buffer length inconsistent with logical field count")
    bits = [(byte >> v) & 1 for byte in buf for v in range(8)]
    if any(bits[logical_bits:]):
        raise ValueError("nonzero byte padding")
    return [sum(bits[h*w+v] << v for v in range(w)) for h in range(count)]


def poly_add(a, b):
    return [x+y for x, y in zip(a, b)]


def poly_mul(a, b):
    """Integer negacyclic multiplication: reduce X^n+1, never q."""
    n = len(a)
    out = [0] * n
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[(i+j) % n] += x*y * (1 if i+j < n else -1)
    return out


def center(z, q):
    r = z % q
    return r-q if 2*r >= q else r


def enc(s, value, a, error, t, q):
    c0 = poly_add(poly_mul(a, s), [t*x for x in error])
    c0[0] += value  # constant polynomial, not all coefficients
    return [x % q for x in c0], [(-x) % q for x in a]


class M1EncodingTests(unittest.TestCase):
    def test_round_trip_boundary_lengths(self):
        rng = random.Random(20260922)
        rho, n = 5, 8
        for j in (n-1, n, n+1, 2*n+1):
            for ell in (j*rho, (j-1)*rho+1, j*rho-1):
                for bits in ([0]*ell, [1]*ell, [rng.randrange(2) for _ in range(ell)]):
                    with self.subTest(j=j, ell=ell, kind=sum(bits)):
                        polys = encode(bits, rho, n)
                        self.assertEqual(shape(ell, rho, n), (j, (j+n-1)//n))
                        self.assertEqual(decode(polys, ell, rho, n), bits)
                        self.assertTrue(all(x < 1 << rho for p in polys for x in p))

    def test_one_bit_and_incomplete_segment(self):
        self.assertEqual(encode([1], 3, 4), [[1, 0, 0, 0]])
        self.assertEqual(encode([1]*7, 3, 4), [[7, 7, 1, 0]])
        self.assertEqual(decode([[7, 7, 1, 0]], 7, 3, 4), [1]*7)

    def test_explicit_bit_order(self):
        self.assertEqual(encode([1, 0, 1, 0, 1, 1], 3, 2), [[5, 6]])

    def test_scalar_exhaustive_alpha_1_2_3(self):
        rho, w = 3, 16
        for weights in ((1,), (1, 8), (1, 8, 64)):
            validate_weights(rho, w, weights)
            for xs in itertools.product(range(1 << rho), repeat=len(weights)):
                with self.subTest(weights=weights, xs=xs):
                    y = pack(xs, rho, w, weights)
                    self.assertLess(y, 1 << w)
                    self.assertEqual(unpack(y, rho, len(weights), 1 << w), xs)

    def test_nonadjacent_targets_reconstruct_in_tuple_order(self):
        rng = random.Random(4281)
        ell, rho, n, w = 53, 3, 4, 16
        database = [[rng.randrange(2) for _ in range(ell)] for _ in range(7)]
        database[0] = [0]*ell
        database[6] = [1]*ell
        encoded = [encode(bits, rho, n) for bits in database]
        for targets, weights in (((6,), (1,)), ((6, 0), (1, 8)), ((0, 6), (1, 8)), ((6, 0, 3), (1, 8, 64))):
            recovered = [[[0]*n for _ in encoded[0]] for _ in targets]
            for j in range(len(encoded[0])):
                for u in range(n):
                    y = pack([encoded[i][j][u] for i in targets], rho, w, weights)
                    xs = unpack(y, rho, len(weights), 1 << w)
                    for r, x in enumerate(xs):
                        recovered[r][j][u] = x
            self.assertEqual([decode(p, ell, rho, n) for p in recovered],
                             [database[i] for i in targets])

    def test_zero_extension_and_full_block_byte_padding(self):
        bits, rho, n, w = [1, 0, 1, 1, 0, 0, 1], 3, 4, 11
        polys = encode(bits, rho, n)
        fields = list(itertools.chain.from_iterable(polys))
        buf = serialize_fields(fields, w)
        self.assertEqual(len(bits), 7)
        self.assertEqual(shape(len(bits), rho, n), (3, 1))
        self.assertEqual(3*w, 33)  # valid field bits
        self.assertEqual(len(fields)*w, 44)  # complete encoded bits
        self.assertEqual(len(buf), 6)  # 48 physical bits
        imported = import_fields(buf, 4, w)
        self.assertEqual(imported, fields)
        self.assertEqual(decode([imported], 7, rho, n), bits)
        logical = int.from_bytes(buf, 'little')
        for h in range(len(fields)):
            self.assertEqual((logical >> (h*w+rho)) & ((1 << (w-rho))-1), 0)

    def test_padding_cannot_create_extra_fields(self):
        buf = serialize_fields([1], 3)  # five byte-padding bits
        self.assertEqual(import_fields(buf, 1, 3), [1])
        self.assertEqual(len(import_fields(buf, 1, 3)), 1)
        with self.assertRaises(ValueError):
            import_fields(buf + b'\0', 1, 3)
        with self.assertRaises(ValueError):
            import_fields(bytes([buf[0] | 0x80]), 1, 3)

    def test_44_bit_fields_remain_exact(self):
        fields = [0, 65535, 1, 0]
        self.assertEqual(import_fields(serialize_fields(fields, 44), 4, 44), fields)

    def test_tight_import_domain_mismatch_regression(self):
        rho, w, weights = 16, 44, (1, 65536)
        # Wrong: concatenate 16-bit segments, then reinterpret as 44-bit fields.
        tight_buf = serialize_fields([1, 1, 0], rho)
        wrong_first_field = int.from_bytes(tight_buf, 'little') & ((1 << w)-1)
        self.assertEqual(wrong_first_field, 65537)
        self.assertGreaterEqual(wrong_first_field, 1 << rho)
        self.assertEqual(weights[0]*wrong_first_field + weights[1]*0,
                         weights[0]*1 + weights[1]*1)
        with self.assertRaisesRegex(ValueError, 'outside legal domain'):
            pack((wrong_first_field, 0), rho, w, weights)
        self.assertEqual(unpack(pack((0, 1), rho, w, weights), rho, len(weights), 1 << w), (0, 1))
        correct_buf = serialize_fields([1, 1, 0], w)
        self.assertEqual(import_fields(correct_buf, 3, w), [1, 1, 0])

    def test_invalid_weights_and_domains_rejected(self):
        for weights in ((2,), (1, 7), (3, 27), (1, 9, 81)):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                validate_weights(3, 16, weights)
        with self.assertRaises(ValueError):
            validate_weights(3, 5, (1, 8))
        with self.assertRaises(ValueError):
            decode([[8, 0, 0, 0]], 1, 3, 4)
        with self.assertRaises(ValueError):
            decode([[1, 0, 0, 1]], 1, 3, 4)
        with self.assertRaises(ValueError):
            decode([[3, 0, 0, 0]], 1, 3, 4)

    def test_radix_capacity_and_order(self):
        for rho in (1, 3, 8, 12, 16):
            B = 1 << rho
            for alpha in (1, 2):
                weights = radix_weights(rho, alpha)
                t = B**alpha
                for xs in itertools.product((0, 1, B-1), repeat=alpha):
                    y = pack(xs, rho, alpha*rho, weights)
                    self.assertEqual(unpack(y, rho, alpha, t), xs)
                    self.assertLess(y, t)
                with self.assertRaises(ValueError):
                    unpack(0, rho, alpha, t-1)
                with self.assertRaises(ValueError):
                    pack((0,)*alpha, rho, alpha*rho-1, weights)
                with self.assertRaises(ValueError):
                    unpack(t, rho, alpha, t*2)
            self.assertEqual(unpack(1+B*(B-1), rho, 2, B**2), (1, B-1))

    def test_radix_record_matrix(self):
        rng = random.Random(404)
        n = 8
        cases = 0
        for rho in (3, 8, 12, 16):
            for J in (n-1, n, n+1, 2*n+1):
                for cut in (0, 1):
                    ell = J*rho-cut
                    db = [[0]*ell, [1]*ell,
                          [rng.randrange(2) for _ in range(ell)]]
                    encoded = [encode(bits, rho, n) for bits in db]
                    for targets in ((0,), (1,), (2,), (1, 2), (2, 1)):
                        alpha = len(targets)
                        weights = radix_weights(rho, alpha)
                        w = alpha*rho  # test equality capacity in every case
                        recovered = [[] for _ in targets]
                        for j in range(len(encoded[0])):
                            ys = [pack([encoded[i][j][u] for i in targets], rho, w, weights)
                                  for u in range(n)]
                            ys = import_fields(serialize_fields(ys, w), n, w)
                            xs = [unpack(y, rho, alpha, 1 << w) for y in ys]
                            for r in range(alpha):
                                recovered[r].append([x[r] for x in xs])
                        self.assertEqual([decode(p, ell, rho, n) for p in recovered],
                                         [db[i] for i in targets])
                        cases += 1
        self.assertEqual(cases, 160)

    def test_negacyclic_integer_ring(self):
        self.assertEqual(poly_mul([0, 0, 0, 1], [0, 1, 0, 0]), [-1, 0, 0, 0])

    def test_ske_reply_congruence_and_conditional_recovery(self):
        rng = random.Random(613)
        n, rho, w, ell, q = 4, 3, 16, 29, (1 << 61)-1
        t, weights, targets = 1 << w, (1, 8, 64), (4, 0, 2)
        records = [[rng.randrange(2) for _ in range(ell)] for _ in range(5)]
        polys = [encode(bits, rho, n) for bits in records]
        s = [rng.randrange(-2, 3) for _ in range(n)]
        errors = [[rng.randrange(-2, 3) for _ in range(n)] for _ in records]
        masks = [[rng.randrange(q) for _ in range(n)] for _ in records]
        selectors = dict(zip(targets, weights))
        query = [enc(s, selectors.get(i, 0), masks[i], errors[i], t, q)
                 for i in range(len(records))]
        recovered = [[] for _ in targets]
        for j in range(len(polys[0])):
            reply = [[0]*n, [0]*n]
            noise = [0]*n
            for i in range(len(records)):
                noise = poly_add(noise, poly_mul(polys[i][j], errors[i]))
                for c in (0, 1):
                    reply[c] = [x % q for x in poly_add(reply[c], poly_mul(polys[i][j], query[i][c]))]
            pm = [sum(k*polys[i][j][u] for i, k in zip(targets, weights)) for u in range(n)]
            z = poly_add(pm, [t*e for e in noise])
            # Pre-mod-q bound, not a circular bound on already centered values.
            self.assertLess(2*(max(map(abs, pm))+t*max(map(abs, noise))), q)
            representative_sum = poly_add(reply[0], poly_mul(reply[1], s))
            self.assertEqual([x % q for x in representative_sum], [x % q for x in z])
            centered = [center(x, q) for x in representative_sum]
            self.assertEqual(centered, z)
            plain = [x % t for x in centered]
            self.assertEqual(plain, pm)
            xs = [unpack(y, rho, len(weights), t) for y in plain]
            for r in range(len(targets)):
                recovered[r].append([x[r] for x in xs])
        self.assertEqual([decode(p, ell, rho, n) for p in recovered], [records[i] for i in targets])

    def test_direct_weight_encryption_does_not_scale_error(self):
        n, q, t, k = 4, 1000003, 256, 8
        s, a, error = [1, -1, 0, 1], [13, 42, 85, 4], [1, -1, 2, 0]
        c0, c1 = enc(s, k, a, error, t, q)
        value = [center(x, q) for x in poly_add(c0, poly_mul(c1, s))]
        self.assertEqual(value, [k+t, -t, 2*t, 0])
        self.assertNotEqual(value, [k+k*t, -k*t, 2*k*t, 0])

    def test_centered_bound_alone_does_not_prove_correctness(self):
        q, t, message, error = 17, 8, 1, 2
        z = message + t*error
        self.assertEqual(z, q)
        self.assertLess(abs(center(z, q)), q/2)
        self.assertNotEqual(center(z, q) % t, message)


if __name__ == '__main__':
    unittest.main()
