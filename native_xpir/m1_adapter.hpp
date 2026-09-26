// S4-0 radix record adapter, exact integer checks, and coefficient Unpack/Decode.
// Tested host contract: x86-64 little endian. No changes to XPIR source.
#pragma once
#include <algorithm>
#include <climits>
#include <cstdint>
#include <stdexcept>
#include <vector>
#include "crypto/NFLLWE.hpp"

namespace m1 {
inline void require(bool ok, const char* reason) {
    if (!ok) throw std::runtime_error(reason);
}
struct Layout {
    uint64_t ell, J, L, encoded_bits, logical_bytes;
    unsigned rho, w, n;
    Layout(uint64_t e, unsigned r, unsigned width, unsigned degree)
        : ell(e),rho(r),w(width),n(degree) {
        require(ell && rho && rho<=w && w<=56, "unsupported adapter width");
        require(n && !(n&(n-1)), "degree not a power of two");
        J=(ell+rho-1)/rho; L=(J+n-1)/n;
        encoded_bits=L*n*w;
        logical_bytes=(encoded_bits+7)/8;
        // Native public importDataNFL takes a byte length, so use complete blocks.
        require(encoded_bits%8==0, "full-block length must be byte-aligned");
    }
    uint64_t t() const { return uint64_t(1)<<w; }
    uint64_t B() const { return uint64_t(1)<<rho; }
};
inline unsigned bit(const std::vector<unsigned char>& b, uint64_t pos) {
    return (b.at(pos/8)>>(pos%8))&1;
}
inline void setbit(std::vector<unsigned char>& b, uint64_t pos, unsigned value) {
    b.at(pos/8)|=static_cast<unsigned char>(value<<(pos%8));
}
inline std::vector<uint64_t> segments(const std::vector<unsigned char>& raw, const Layout& l) {
    require(raw.size()==(l.ell+7)/8, "original byte count mismatch");
    if (l.ell%8) require((raw.back()>>(l.ell%8))==0, "nonzero unused original byte bits");
    std::vector<uint64_t> x(l.L*l.n,0);
    for(uint64_t p=0;p<l.ell;++p) x[p/l.rho]|=uint64_t(bit(raw,p))<<(p%l.rho);
    return x;
}
inline std::vector<unsigned char> adapt(const std::vector<unsigned char>& raw, const Layout& l) {
    const auto x=segments(raw,l);
    std::vector<unsigned char> out(l.logical_bytes,0);
    for(uint64_t h=0;h<x.size();++h)
        for(unsigned v=0;v<l.rho;++v) setbit(out,h*l.w+v,(x[h]>>v)&1);
    return out;
}
inline std::vector<uint64_t> read_fields(const unsigned char* p, uint64_t count, unsigned w) {
    std::vector<uint64_t> result(count,0);
    for(uint64_t h=0;h<count;++h)
        for(unsigned v=0;v<w;++v)
            result[h]|=uint64_t((p[(h*w+v)/8]>>((h*w+v)%8))&1)<<v;
    return result;
}
inline std::vector<uint64_t> radix_weights(const Layout& l, size_t alpha) {
    require(alpha>0 && alpha<=l.w/l.rho, "insufficient radix plaintext capacity");
    std::vector<uint64_t> K(alpha);
    for(size_t r=0;r<alpha;++r) K[r]=uint64_t(1)<<(l.rho*r);
    return K;
}
inline void validate_weights(const Layout& l, const std::vector<uint64_t>& K) {
    require(K==radix_weights(l,K.size()), "weights are not derived radix powers");
    for(uint64_t k:K)
        require(k<=UINT_MAX, "weight exceeds native unsigned int API; no truncation");
}
inline char* encrypt_integer(NFLLWE& client, uint64_t value) {
    const unsigned w=client.publicParams.getAbsorptionBitsize()/client.getpolyDegree();
    require(w>0 && w<64, "unsupported encryption field width");
    require(value<=UINT_MAX && value<(uint64_t(1)<<w), "integer does not fit API/plaintext field");
    return client.encrypt(static_cast<unsigned int>(value),1); // exactly one direct call
}
inline std::vector<uint64_t> unpack(uint64_t y, const Layout& l, size_t alpha) {
    const auto K=radix_weights(l,alpha);
    require(y<(uint64_t(1)<<(l.rho*alpha)), "coefficient outside radix image");
    std::vector<uint64_t> x(alpha);
    for(size_t r=0;r<alpha;++r) x[r]=(y/K[r])%l.B();
    return x;
}
inline std::vector<unsigned char> decode(const std::vector<uint64_t>& x, const Layout& l) {
    require(x.size()==l.L*l.n, "wrong decoded field count");
    for(uint64_t h=0;h<x.size();++h) {
        require(x[h]<l.B(), "decoded segment out of domain");
        if(h>=l.J) require(x[h]==0, "nonzero polynomial padding");
    }
    if(l.ell%l.rho) require((x[l.J-1]>>(l.ell%l.rho))==0, "nonzero final segment padding");
    std::vector<unsigned char> out((l.ell+7)/8,0);
    for(uint64_t p=0;p<l.ell;++p) setbit(out,p,(x[p/l.rho]>>(p%l.rho))&1);
    return out;
}
} // namespace m1
