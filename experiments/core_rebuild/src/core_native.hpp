// SPDX-License-Identifier: GPL-3.0-or-later
// Project-owned wrapper around the unchanged pinned XPIR interface.
#pragma once

// Load POSIX declarations before XPIR headers introduce broad using-directives.
#include <sys/types.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <sched.h>
#include <signal.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <gmpxx.h>
#include "crypto/NFLLWE.hpp"
#include "pir/replyGenerator/PIRReplyGeneratorNFL_internal.hpp"

namespace core_rebuild {
using Bytes = std::vector<unsigned char>;
using Database = std::vector<Bytes>;
constexpr uint64_t DEGREE = 4096, WIDTH = 24, CIPHER_BYTES = 131072;
constexpr uint64_t P1 = 2305843009213317121ULL, P2 = 2305843009213120513ULL;
constexpr uint64_t DATA_OFFSET = 4096, ERROR_MAX = 398;
constexpr const char* MODULUS = "5316911983137472318178862960259203073";

inline void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
inline uint64_t checked_product(uint64_t a, uint64_t b) {
    require(!b || a <= std::numeric_limits<uint64_t>::max()/b, "size multiplication overflow");
    return a*b;
}
struct Layout {
    uint64_t ell, rho, J, L, field_bytes, record_bytes;
    Layout(uint64_t bits, uint64_t segment) : ell(bits), rho(segment) {
        require(ell && rho && rho <= WIDTH, "invalid record length/segment width");
        require(ell <= std::numeric_limits<uint64_t>::max()-(rho-1), "record length overflow");
        J = (ell+rho-1)/rho;
        L = (J+DEGREE-1)/DEGREE;
        field_bytes = checked_product(checked_product(L, DEGREE), WIDTH)/8;
        record_bytes = (ell+7)/8;
    }
    uint64_t B() const { return uint64_t(1) << rho; }
    uint64_t t() const { return uint64_t(1) << WIDTH; }
    uint64_t fields() const { return checked_product(L, DEGREE); }
    std::vector<uint64_t> weights(size_t alpha) const {
        require(alpha >= 1 && alpha <= 4 && alpha*rho <= WIDTH, "insufficient packed capacity");
        std::vector<uint64_t> result(alpha);
        for (size_t i=0; i<alpha; ++i) {
            result[i] = uint64_t(1) << (i*rho);
            require(result[i] <= UINT32_MAX && result[i] < t(), "direct weight does not fit API");
        }
        return result;
    }
    std::vector<uint64_t> segments(const Bytes& raw) const {
        require(raw.size() == record_bytes, "wrong original byte count");
        if (ell%8) require((raw.back() >> (ell%8)) == 0, "unused original bits nonzero");
        std::vector<uint64_t> result(fields(), 0);
        for (uint64_t bit=0; bit<ell; ++bit)
            result[bit/rho] |= uint64_t((raw[bit/8] >> (bit%8))&1) << (bit%rho);
        return result;
    }
    Bytes encode(const Bytes& raw) const {
        const auto values=segments(raw);
        Bytes result(field_bytes,0);
        for (uint64_t i=0; i<values.size(); ++i)
            for (uint64_t bit=0; bit<rho; ++bit) {
                uint64_t pos=i*WIDTH+bit;
                result[pos/8] |= ((values[i]>>bit)&1) << (pos%8);
            }
        return result;
    }
    Bytes decode(const std::vector<uint64_t>& values) const {
        require(values.size() == fields(), "wrong segment count");
        for (uint64_t i=0; i<values.size(); ++i) {
            require(values[i] < B(), "segment exceeds radix");
            if (i>=J) require(values[i] == 0, "polynomial padding nonzero");
        }
        if (ell%rho) require((values[J-1]>>(ell%rho)) == 0, "final segment padding nonzero");
        Bytes result(record_bytes,0);
        for (uint64_t bit=0; bit<ell; ++bit)
            result[bit/8] |= ((values[bit/rho]>>(bit%rho))&1) << (bit%8);
        return result;
    }
};

inline uint64_t splitmix(uint64_t& state) {
    uint64_t z=(state+=0x9e3779b97f4a7c15ULL);
    z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;
    z=(z^(z>>27))*0x94d049bb133111ebULL;
    return z^(z>>31);
}
inline Database fixture(uint64_t N, const Layout& layout, uint64_t seed, const std::string& kind) {
    require(N && N <= UINT32_MAX, "invalid database count");
    Database db(N, Bytes(layout.record_bytes));
    uint64_t state=seed ^ (N << 32) ^ layout.ell;
    require(kind=="pseudorandom" || kind=="zero" || kind=="max" || kind=="alternating" || kind=="equal", "unknown fixture kind");
    for (uint64_t i=0; i<N; ++i) {
        for (uint64_t j=0; j<layout.record_bytes; j+=8) {
            uint64_t word=splitmix(state);
            for (uint64_t k=0; k<8 && j+k<layout.record_bytes; ++k) {
                unsigned char b=(word>>(8*k))&255;
                if (kind=="zero") b=0;
                if (kind=="max") b=255;
                if (kind=="alternating") b=((i+j+k)%2)?0x55:0xaa;
                db[i][j+k]=b;
            }
        }
        if (layout.ell%8) db[i].back() &= (1u << (layout.ell%8))-1;
    }
    if (kind=="equal") for (uint64_t i=1; i<N; ++i) db[i]=db[0];
    return db;
}

inline void configure_key(NFLLWE& crypto) {
    crypto.setsecurityBits(0); // Legacy initialization field; not a security-level assertion.
    crypto.setNewParameters(DEGREE,120,WIDTH); // Actual fresh native KeyGen.
    crypto.publicParams.setnoiseUB(200);
    crypto.recomputeNoiseAmplifiers();
    require(crypto.getpolyDegree()==DEGREE && crypto.getnbModuli()==2, "backend degree/modulus count changed");
    require(crypto.getmoduli()[0]==P1 && crypto.getmoduli()[1]==P2, "backend primes changed");
    mpz_t product; crypto.getnflInstance().copymoduliProduct(product);
    mpz_class q(product); mpz_clear(product);
    require(q==mpz_class(MODULUS), "backend modulus product changed");
    require(crypto.publicParams.getAbsorptionBitsize()==DEGREE*WIDTH, "actual absorption width changed");
    require(crypto.publicParams.getnoiseUB()==200, "actual error setting changed");
    require(crypto.publicParams.getCiphertextBitsize()/8==CIPHER_BYTES, "ciphertext ABI changed");
}
inline void sufficient_screen(uint64_t N, const Layout& layout, size_t alpha) {
    layout.weights(alpha);
    const mpz_class A=(mpz_class(1) << (alpha*layout.rho))-1;
    const mpz_class t=mpz_class(1) << WIDTH;
    for (uint64_t block=0; block<layout.L; ++block) {
        const uint64_t eta=std::min(DEGREE, layout.J-block*DEGREE);
        mpz_class bound=A+t*mpz_class(N)*mpz_class(eta)*mpz_class(layout.B()-1)*mpz_class(ERROR_MAX);
        require(2*bound < mpz_class(MODULUS), "finite-configuration no-wrap sufficient screen failed");
    }
}
inline void transfer(int fd, void* memory, size_t count, bool write_mode) {
    char* cursor=static_cast<char*>(memory);
    while (count) {
        ssize_t n=write_mode ? ::write(fd,cursor,count) : ::read(fd,cursor,count);
        if (n<0 && errno==EINTR) continue;
        require(n>0, "pipe/file transfer failed");
        cursor+=n; count-=n;
    }
}

struct MemoryDatabase : DBHandler {
    Database encoded;
    std::vector<uint64_t> offsets;
    explicit MemoryDatabase(Database values) : encoded(std::move(values)), offsets(encoded.size(),0) {}
    std::string getCatalog(bool) override { return "core-rebuild public fixture"; }
    uint64_t getNbStream() override { return encoded.size(); }
    uint64_t getmaxFileBytesize() override { return encoded.at(0).size(); }
    bool openStream(uint64_t i,uint64_t offset) override { offsets.at(i)=offset; return true; }
    uint64_t readStream(uint64_t i,char* out,uint64_t count) override {
        require(offsets.at(i)+count <= encoded.at(i).size(), "database read outside layout");
        std::memcpy(out,encoded[i].data()+offsets[i],count); offsets[i]+=count; return count;
    }
    void closeStream(uint64_t) override {}
};
struct ImportedOwnerReply : PIRReplyGeneratorNFL_internal {
    ImportedOwnerReply(PIRParameters& params,MemoryDatabase& db,NFLLWE& crypto)
      : PIRReplyGeneratorNFL_internal(params,&db) { mutex.unlock(); setCryptoMethod(&crypto); }
    lwe_in_data* imported() { return input_data; }
    uint64_t blocks() const { return currentMaxNbPolys; }
    ~ImportedOwnerReply() {
        // importDataNFL uses malloc for all three allocation layers. Do not call its legacy delete[] path.
        if (input_data) {
            for (uint64_t i=0; i<pirParam.n[0]; ++i) {
                if (input_data[i].p) { std::free(input_data[i].p[0]); std::free(input_data[i].p); }
            }
            std::free(input_data); input_data=nullptr;
        }
    }
};

struct SharedHeader {
    char magic[8];
    uint64_t version,N,ell,rho,n,w,J,L,p1,p2,data_bytes,fixture_seed;
};
static_assert(sizeof(SharedHeader) <= DATA_OFFSET,"mapping header exceeds data offset");
inline uint64_t imported_bytes(uint64_t N,const Layout& layout) {
    return checked_product(checked_product(checked_product(N,layout.L),DEGREE*2),sizeof(uint64_t));
}
inline void export_mapping(const std::string& path,lwe_in_data* rows,uint64_t N,
                           const Layout& layout,uint64_t seed,int db_fd=-1) {
    const int fd=db_fd>=0 ? ::dup(db_fd) : ::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);
    require(fd>=0,"shared mapping output exists or cannot be created");
    try {
        struct stat info{};require(::fstat(fd,&info)==0 && info.st_size==0,"mapping owner requires empty output");
        require(::lseek(fd,0,SEEK_SET)==0,"cannot position shared mapping owner");
        SharedHeader h{};std::memcpy(h.magic,"COREXPIR",8);
        h.version=1; h.N=N; h.ell=layout.ell; h.rho=layout.rho; h.n=DEGREE; h.w=WIDTH;
        h.J=layout.J; h.L=layout.L; h.p1=P1; h.p2=P2;
        h.data_bytes=imported_bytes(N,layout); h.fixture_seed=seed;
        std::array<unsigned char,DATA_OFFSET> prefix{};std::memcpy(prefix.data(),&h,sizeof(h));
        transfer(fd,prefix.data(),prefix.size(),true);
        for (uint64_t i=0; i<N; ++i) {
            require(rows[i].nbPolys==layout.L,"native import block count changed");
            for (uint64_t block=0; block<layout.L; ++block)
                transfer(fd,rows[i].p[block],DEGREE*2*sizeof(uint64_t),true);
        }
        require(::fchmod(fd,0444)==0,"cannot mark shared mapping read-only");
        require(::close(fd)==0,"cannot close shared mapping");
    } catch (...) { ::close(fd); throw; }
}
class ReadOnlyMapping {
    int fd_=-1;
    void* address_=MAP_FAILED;
    size_t bytes_=0;
public:
    SharedHeader header{};
    ReadOnlyMapping(const std::string& path,uint64_t N,const Layout& layout,uint64_t seed) {
        fd_=::open(path.c_str(),O_RDONLY);
        require(fd_>=0,"cannot open shared mapping read-only");
        try {
            struct stat info{}; require(::fstat(fd_,&info)==0 && info.st_size>=static_cast<off_t>(DATA_OFFSET),"short shared mapping");
            bytes_=info.st_size;
            address_=::mmap(nullptr,bytes_,PROT_READ,MAP_SHARED,fd_,0);
            require(address_!=MAP_FAILED,"shared read-only mmap failed");
            std::memcpy(&header,address_,sizeof(header));
            require(std::memcmp(header.magic,"COREXPIR",8)==0 && header.version==1,"mapping schema mismatch");
            require(header.N==N && header.ell==layout.ell && header.rho==layout.rho && header.J==layout.J && header.L==layout.L,"mapping layout mismatch");
            require(header.n==DEGREE && header.w==WIDTH && header.p1==P1 && header.p2==P2,"mapping backend mismatch");
            require(header.fixture_seed==seed,"mapping fixture seed mismatch");
            require(header.data_bytes==imported_bytes(N,layout) && bytes_==DATA_OFFSET+header.data_bytes,"mapping byte count mismatch");
        } catch (...) {
            if (address_!=MAP_FAILED) ::munmap(address_,bytes_);
            ::close(fd_); throw;
        }
    }
    ReadOnlyMapping(const ReadOnlyMapping&)=delete;
    ReadOnlyMapping& operator=(const ReadOnlyMapping&)=delete;
    ~ReadOnlyMapping() { if (address_!=MAP_FAILED) ::munmap(address_,bytes_); if(fd_>=0) ::close(fd_); }
    const uint64_t* data() const { return reinterpret_cast<const uint64_t*>(static_cast<const unsigned char*>(address_)+DATA_OFFSET); }
    size_t bytes() const { return bytes_; }
};
struct BorrowedReply : PIRReplyGeneratorNFL_internal {
    std::vector<lwe_in_data> rows;
    std::vector<std::vector<poly64>> pointers;
    BorrowedReply(PIRParameters& params,NFLLWE& crypto,const ReadOnlyMapping& mapping)
      : PIRReplyGeneratorNFL_internal(params,nullptr),rows(params.n[0]),pointers(params.n[0]) {
        require(params.d==1 && params.alpha==1,"only flat nonaggregated path permitted");
        mutex.unlock(); setCryptoMethod(&crypto);
        for (uint64_t i=0; i<rows.size(); ++i) {
            pointers[i].resize(mapping.header.L);
            for (uint64_t b=0; b<mapping.header.L; ++b)
                pointers[i][b]=const_cast<poly64>(mapping.data()+(i*mapping.header.L+b)*DEGREE*2);
            rows[i].p=pointers[i].data(); rows[i].nbPolys=mapping.header.L;
        }
        input_data=rows.data(); currentMaxNbPolys=mapping.header.L;
        initQueriesBuffer();
    }
    void evaluate() { repliesAmount=currentMaxNbPolys; repliesIndex=0; generateReply(); }
    ~BorrowedReply() { input_data=nullptr; } // Private pointer tables own no mapped coefficient storage.
};
} // namespace core_rebuild
