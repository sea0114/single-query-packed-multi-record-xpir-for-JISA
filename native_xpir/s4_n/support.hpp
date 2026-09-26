// S4-N explicit-width flat adapter. Pinned XPIR and the S4-0 adapter are unchanged.
#pragma once
#include "../m1_adapter.hpp"
#include "pir/replyGenerator/PIRReplyGeneratorNFL_internal.hpp"
#include <gmpxx.h>
#include <cstring>
#include <functional>
#include <set>
#include <string>
#include <sys/resource.h>
namespace s4n {
using m1::require;
constexpr unsigned DEGREE=4096;
constexpr uint64_t P1=2305843009213317121ULL,P2=2305843009213120513ULL;
constexpr uint64_t BERR=200;
const char* const Q="5316911983137472318178862960259203073";

// No clock is read here. B0 can attach a callback to these phase boundaries.
struct Hooks {
    std::vector<std::string> events;
    std::function<void(const std::string&,bool)> observer;
    void mark(const std::string& phase,bool begin) {
        events.push_back(phase+(begin?":begin":":end"));
        if(observer) observer(phase,begin);
    }
};
struct Phase {
    Hooks& hooks; std::string name;
    Phase(Hooks& h,const std::string& n):hooks(h),name(n) {hooks.mark(name,true);}
    ~Phase() {hooks.mark(name,false);}
};
inline bool peak_memory_hook_available() {
    struct rusage usage{};
    return getrusage(RUSAGE_SELF,&usage)==0 && usage.ru_maxrss>0;
}
inline void check_backend(NFLLWE& crypto,unsigned w) {
    require(crypto.getpolyDegree()==DEGREE && crypto.getnbModuli()==2,"fixed n/Q2 mismatch");
    require(crypto.getmoduli()[0]==P1 && crypto.getmoduli()[1]==P2,"fixed prime set mismatch");
    mpz_t product; crypto.getnflInstance().copymoduliProduct(product);
    mpz_class actual(product); mpz_clear(product);
    require(actual==mpz_class(Q),"internal GMP q mismatch");
    require(crypto.publicParams.getAbsorptionBitsize()==DEGREE*w,"explicit width mismatch");
    require(crypto.publicParams.getnoiseUB()==BERR,"Berr configuration mismatch");
    require(crypto.publicParams.getCiphertextBitsize()/8==2*2*DEGREE*sizeof(uint64_t),"ciphertext ABI");
    mpz_class modulus=mpz_class(1)<<w;
    require(modulus==mpz_class(uint64_t(1)<<w),"plaintext modulus representation overflow");
    if(w==32) require(modulus==mpz_class("4294967296"),"t=2^32 overflow");
}
inline void configure_and_keygen(NFLLWE& crypto,unsigned w) {
    crypto.setsecurityBits(0); // Initialize a legacy slot; NOT a security level.
    crypto.setNewParameters(DEGREE,120,w); // Actual native KeyGen and exact public width.
    crypto.publicParams.setnoiseUB(BERR);
    crypto.recomputeNoiseAmplifiers(); // GMP 2^w -> uint64_t RNS amplifiers.
    check_backend(crypto,w);
}
inline void validate_layout(const m1::Layout& l) {
    m1::Layout expected(l.ell,l.rho,l.w,l.n);
    require(l.n==DEGREE && l.J==expected.J && l.L==expected.L &&
            l.encoded_bits==expected.encoded_bits && l.logical_bytes==expected.logical_bytes,
            "malformed layout");
}
inline void validate_targets(unsigned N,const std::vector<unsigned>& targets) {
    require(!targets.empty() && targets.size()<=N,"target count");
    std::set<unsigned> seen;
    for(auto i:targets) require(i<N && seen.insert(i).second,"duplicate or out-of-range target");
}
inline void validate_encoded(const std::vector<unsigned char>& bytes,const m1::Layout& l) {
    validate_layout(l);
    require(bytes.size()==l.logical_bytes,"wrong encoded length");
    // Also checks final-segment and polynomial padding, and every field's domain.
    m1::decode(m1::read_fields(bytes.data(),l.L*l.n,l.w),l);
}
class MemoryDB : public DBHandler {
public:
    std::vector<std::vector<unsigned char>> data;
    std::vector<uint64_t> offsets;
    uint64_t reads=0;
    MemoryDB(std::vector<std::vector<unsigned char>> d,const m1::Layout& l):
        data(std::move(d)),offsets(data.size(),0) {
        require(!data.empty(),"empty database");
        for(const auto& x:data) validate_encoded(x,l);
    }
    std::string getCatalog(bool) override {return "S4-N deterministic functional fixtures";}
    uint64_t getNbStream() override {return data.size();}
    uint64_t getmaxFileBytesize() override {return data.at(0).size();}
    bool openStream(uint64_t i,uint64_t o) override {offsets.at(i)=o;return true;}
    uint64_t readStream(uint64_t i,char* out,uint64_t count) override {
        require(offsets.at(i)+count<=data.at(i).size(),"read beyond encoded layout");
        std::memcpy(out,data[i].data()+offsets[i],count); offsets[i]+=count; ++reads;
        return count;
    }
    void closeStream(uint64_t) override {}
};
class NativeReply : public PIRReplyGeneratorNFL_internal {
public:
    NativeReply(PIRParameters& p,MemoryDB& db,NFLLWE& server):
        PIRReplyGeneratorNFL_internal(p,&db) {
        require(p.d==1 && p.alpha==1 && p.n[0]==db.data.size(),"flat recursion/aggregation mismatch");
        mutex.unlock(); // Same synchronous ownership model as the old harness.
        setCryptoMethod(&server);
        // Constructor already stored pirParam. Use native buffer initialization directly:
        // setPirParams() would overwrite exact w via its legacy heuristic.
        initQueriesBuffer();
    }
    lwe_in_data* imported() {return input_data;}
    uint64_t blocks() const {return currentMaxNbPolys;}
    void evaluate() {
        require(input_data && currentMaxNbPolys,"reply without actual imported database");
        repliesAmount=currentMaxNbPolys; repliesIndex=0;
        generateReply(); // Entire pinned native orchestration and private FMA loop.
    }
    ~NativeReply() {
        // Match the native malloc allocator; the legacy freeInputData has delete[].
        if(input_data) {
            for(unsigned i=0;i<pirParam.n[0];++i) {
                free(input_data[i].p[0]); free(input_data[i].p);
            }
            free(input_data); input_data=nullptr;
        }
    }
};
inline std::vector<uint64_t> decrypt_fields(NFLLWE& client,char* ciphertext,unsigned w) {
    char* raw=client.decrypt(ciphertext,1,client.publicParams.getCiphertextBitsize()/8,DEGREE*w/8);
    require(raw!=nullptr,"native decrypt returned null");
    auto result=m1::read_fields(reinterpret_cast<unsigned char*>(raw),DEGREE,w);
    free(raw); return result;
}
// Audit the N already-created query ciphertexts; never create diagnostic ciphertexts.
inline uint64_t audit_query(NFLLWE& client,char* c,uint64_t value,unsigned w) {
    auto* words=reinterpret_cast<uint64_t*>(c);
    std::vector<uint64_t> residues(DEGREE*2),errors(DEGREE);
    for(unsigned cm=0;cm<2;++cm) for(unsigned u=0;u<DEGREE;++u) {
        uint64_t p=client.getmoduli()[cm];
        uint64_t as=static_cast<__uint128_t>(words[cm*DEGREE+u])*client.getsecretKey()[cm][u]%p;
        residues[cm*DEGREE+u]=(words[2*DEGREE+cm*DEGREE+u]+p-as)%p;
    }
    client.getnflInstance().invnttAndPowInvPhi(residues.data());
    uint64_t maximum=0;
    for(unsigned cm=0;cm<2;++cm) {
        mpz_class p=client.getmoduli()[cm],t=mpz_class(1)<<w,inv;
        require(mpz_invert(inv.get_mpz_t(),t.get_mpz_t(),p.get_mpz_t())!=0,"invalid noise amplifier");
        uint64_t invt=inv.get_ui();
        for(unsigned u=0;u<DEGREE;++u) {
            uint64_t msg=u==0?value:0,prime=client.getmoduli()[cm];
            uint64_t e=static_cast<__uint128_t>((residues[cm*DEGREE+u]+prime-msg)%prime)*invt%prime;
            require(e<=2*BERR-2,"query is not exact constant + native bounded error");
            if(cm==0) errors[u]=e; else require(errors[u]==e,"shared error CRT mismatch");
            maximum=std::max(maximum,e);
        }
    }
    return maximum;
}
inline void check_import(NFLLWE& server,lwe_in_data* imported,
                         const std::vector<std::vector<uint64_t>>& expected,const m1::Layout& l) {
    for(size_t i=0;i<expected.size();++i) {
        require(imported[i].nbPolys==l.L,"import block count");
        for(uint64_t j=0;j<l.L;++j) {
            std::vector<uint64_t> copy(imported[i].p[j],imported[i].p[j]+DEGREE*2);
            server.getnflInstance().invnttAndPowInvPhi(copy.data());
            for(unsigned cm=0;cm<2;++cm) for(unsigned u=0;u<DEGREE;++u)
                require(copy[cm*DEGREE+u]==expected[i][j*DEGREE+u],"A: imported coefficient mismatch");
        }
    }
}
} // namespace s4n
