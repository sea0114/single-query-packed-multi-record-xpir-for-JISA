// B2-A functional-only harness. Existing adapters and pinned arithmetic are read-only.
#include "../../native_xpir/s4_n/support.hpp"
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <openssl/sha.h>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <limits>
#include <unistd.h>
using s4n::require;
using boost::property_tree::ptree;
using Bytes=std::vector<unsigned char>;
static uint64_t rng_count=0;
static std::vector<uint64_t> rng_sizes;
extern "C" int __real_crypto_stream_salsa20_amd64_xmm6(unsigned char*,unsigned long long,const unsigned char*,const unsigned char*);
extern "C" int __wrap_crypto_stream_salsa20_amd64_xmm6(unsigned char* out,unsigned long long len,const unsigned char* nonce,const unsigned char* key) {
    uint64_t observed=0;for(unsigned i=0;i<8;++i)observed|=uint64_t(nonce[i])<<(8*i);
    require(observed==rng_count,"fresh process Salsa20 nonce sequence");
    ++rng_count;rng_sizes.push_back(len);
    return __real_crypto_stream_salsa20_amd64_xmm6(out,len,nonce,key);
}
static std::string hex(const unsigned char* p,size_t n) {
    std::ostringstream out;for(size_t i=0;i<n;++i)out<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(p[i]);return out.str();
}
static std::string b2_sha256(const unsigned char* p,size_t n) {unsigned char h[SHA256_DIGEST_LENGTH];SHA256(p,n,h);return hex(h,sizeof(h));}
static std::string db_hash(const std::vector<Bytes>& rows) {
    SHA256_CTX ctx;SHA256_Init(&ctx);for(const auto& row:rows)SHA256_Update(&ctx,row.data(),row.size());
    unsigned char h[SHA256_DIGEST_LENGTH];SHA256_Final(h,&ctx);return hex(h,sizeof(h));
}
template<class T> static ptree b2_json_array(const std::vector<T>& values) {
    ptree out;for(const auto& v:values){ptree e;e.put("",v);out.push_back({"",e});}return out;
}
static void save(const std::string& path,const ptree& result) {
    std::ofstream out(path);require(bool(out),"result open");boost::property_tree::write_json(out,result);out.flush();require(bool(out),"result write");
}
static std::vector<unsigned> canonical(unsigned N,unsigned alpha) {
    std::vector<unsigned> result;for(unsigned r=1;r<=alpha;++r)result.push_back(((2*r-1)*N)/(2*alpha));return result;
}
static std::vector<Bytes> fixture(unsigned N,uint64_t ell,uint64_t seed,bool boundary) {
    uint64_t state=seed^(uint64_t(N)<<32)^ell;std::vector<Bytes> rows;
    for(unsigned i=0;i<N;++i){
        Bytes raw;
        for(uint64_t chunk=0;chunk<(ell+63)/64;++chunk){
            state+=0x9e3779b97f4a7c15ULL;uint64_t z=state;
            z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;z=(z^(z>>27))*0x94d049bb133111ebULL;z^=z>>31;
            for(unsigned k=0;k<8;++k)raw.push_back((z>>(8*k))&255);
        }
        raw.resize((ell+7)/8);if(boundary)std::fill(raw.begin(),raw.end(),255);
        if(ell%8)raw.back()&=(1u<<(ell%8))-1;rows.push_back(std::move(raw));
    }
    return rows;
}

static void probe(const std::string& path) {
    ptree result,widths,frontier,output_probes,narrowing;
    result.put("timing_label","FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE");result.put("encrypted",false);
    result.put("unsigned_int_bits",sizeof(unsigned int)*CHAR_BIT);result.put("UINT_MAX",UINT_MAX);
    result.put("uint64_bits",sizeof(uint64_t)*CHAR_BIT);result.put("upstream_width_setter_has_range_guard",false);
    for(unsigned w=1;w<=64;++w){
        bool accepted=false;std::string reason;
        try{m1::Layout l(257,1,w,4096);accepted=true;}catch(const std::runtime_error& e){reason=e.what();}
        require(accepted==(w<=56),"unexpected existing width guard");
        ptree v;v.put("w",w);v.put("accepted_by_existing_adapter",accepted);v.put("reason",reason);widths.push_back({"",v});
    }
    for(unsigned alpha:{2u,3u,4u})for(unsigned rho:{8u,12u,16u}){
        unsigned w=alpha*rho;std::vector<uint64_t> K;for(unsigned r=0;r<alpha;++r)K.push_back(uint64_t(1)<<(r*rho));
        bool width=true,weight=true,whole=true;std::string reason;
        try{m1::Layout l(257,rho,w,4096);}catch(const std::runtime_error&){width=false;}
        for(uint64_t k:K)if(k>UINT_MAX)weight=false;
        try{m1::Layout l(257,rho,w,4096);m1::validate_weights(l,K);}catch(const std::runtime_error& e){whole=false;reason=e.what();}
        require(whole==(width&&weight),"guard conjunction mismatch");
        ptree v;v.put("alpha",alpha);v.put("rho_0",rho);v.put("w",w);v.add_child("weights",b2_json_array(K));
        v.put("native_width_allowed",width);v.put("all_weights_representable",weight);v.put("accepted_before_crypto",whole);
        v.put("guard_rejection_reason",reason);v.put("encrypted",false);v.put("rejected_before_native_conversion",!whole);
        v.put("classification",whole?"NATIVE_CANDIDATE_ADMISSIBLE":(!width&&!weight?"NATIVE_WIDTH_AND_WEIGHT_API_LIMITED":(!width?"NATIVE_WIDTH_LIMITED":"NATIVE_WEIGHT_API_LIMITED")));
        frontier.push_back({"",v});
    }
    for(unsigned exponent:{32u,36u,48u}){
        uint64_t exact=uint64_t(1)<<exponent;
        // This is a defined, isolated C++ type-conversion diagnostic, never a crypto input.
        unsigned int narrowed=static_cast<unsigned int>(exact);
        require(exact>UINT_MAX && narrowed==0,"unexpected unsigned-int ABI");
        ptree v;v.put("exact_value",exact);v.put("exponent",exponent);v.put("representable",false);
        v.put("unguarded_conversion_value",narrowed);v.put("crypto_called",false);
        v.put("meaning","Defined unsigned narrowing would lose the value; existing checked adapter rejects before this conversion.");
        narrowing.push_back({"",v});
    }
    NFLlib lib;lib.setNewParameters(4096,120);
    require(lib.getnbModuli()==2 && lib.getmoduli()[0]==s4n::P1 && lib.getmoduli()[1]==s4n::P2,"probe n/Q2");
    for(unsigned w:{16u,24u,32u,36u,48u,56u}){
        uint64_t max=(uint64_t(1)<<w)-1;unsigned limbs=(w+31)/32;
        std::vector<uint64_t> fields(4096);std::vector<uint32_t> words(4096*limbs,0);
        Bytes expected(4096*w/8+16,0),serialized(expected.size(),0);
        for(unsigned i=0;i<4096;++i){
            uint64_t choices[]={0,1,max,w>32?(uint64_t(1)<<32):max,max-1};fields[i]=choices[i%5];
            for(unsigned b=0;b<w;++b)m1::setbit(expected,uint64_t(i)*w+b,(fields[i]>>b)&1);
            for(unsigned k=0;k<limbs;++k)words[i*limbs+k]=static_cast<uint32_t>(fields[i]>>(32*k));
        }
        lib.serializeData32(words.data(),serialized.data(),w,words.size());
        require(expected==serialized,"serializeData32 round trip/trailing padding");
        require(m1::read_fields(serialized.data(),4096,w)==fields,"output field reconstruction");
        unsigned char* input=expected.data();uint64_t blocks=0;
        auto polynomials=lib.deserializeDataNFL(&input,1,uint64_t(4096)*w,w,blocks);
        require(blocks==1,"importer block count");lib.invnttAndPowInvPhi(polynomials[0]);
        for(unsigned cm=0;cm<2;++cm)for(unsigned i=0;i<4096;++i)require(polynomials[0][cm*4096+i]==fields[i],"full width importer");
        free(polynomials[0]);free(polynomials);
        ptree v;v.put("w",w);v.put("maximum_tested",max);v.put("importer_coefficients_checked",8192);
        v.put("serialized_coefficients_checked",4096);v.put("native_uint32_limbs_per_field",limbs);
        v.put("serialized_bytes_sha256",b2_sha256(serialized.data(),4096*w/8));v.put("status","PASS");v.put("encrypted",false);
        output_probes.push_back({"",v});
    }
    require(rng_count==0,"API probe unexpectedly generated key/encryption randomness");
    result.add_child("width_tests",widths);result.add_child("frontier",frontier);result.add_child("output_probes",output_probes);
    result.add_child("unsafe_raw_api_narrowing_diagnostics",narrowing);result.put("rng_calls",rng_count);result.put("status","PASS");
    save(path,result);
}

static void run_case(const ptree& job,const std::string& path){
    const std::string label="FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE";
    require(job.get<std::string>("timing_label")==label,"functional-only label required");
    unsigned alpha=job.get<unsigned>("alpha"),rho=job.get<unsigned>("rho_0"),w=job.get<unsigned>("w"),N=job.get<unsigned>("N");
    uint64_t ell=job.get<uint64_t>("ell_bits"),seed=job.get<uint64_t>("fixture_seed");
    bool boundary=job.get<bool>("boundary");std::string order=job.get<std::string>("order_mode");
    require((alpha==3||alpha==4) && (N==8||N==32) && w==alpha*rho,"B2 functional domain");
    m1::Layout l(ell,rho,w,4096);s4n::validate_layout(l);
    auto K=m1::radix_weights(l,alpha);m1::validate_weights(l,K); // Before any keygen/encryption.
    std::vector<unsigned> requested;for(const auto& x:job.get_child("targets"))requested.push_back(x.second.get_value<unsigned>());
    auto canonical_targets=canonical(N,alpha);if(order=="reverse")std::reverse(canonical_targets.begin(),canonical_targets.end());
    require(requested==canonical_targets && requested.size()==alpha,"canonical requested order");s4n::validate_targets(N,requested);
    require(rng_count==0,"process must contain exactly one fresh task");
    NFLLWE server,client;s4n::configure_and_keygen(server,w);s4n::configure_and_keygen(client,w);
    require(rng_count==2 && rng_sizes[0]==4096*2*8 && rng_sizes[1]==4096*2*8,"one client and legacy unused server key");
    std::string key_fingerprint=b2_sha256(reinterpret_cast<const unsigned char*>(client.getsecretKey()[0]),4096*2*sizeof(uint64_t));
    auto raw=fixture(N,ell,seed,boundary);std::vector<Bytes> encoded;std::vector<std::vector<uint64_t>> fields;
    for(const auto& record:raw){encoded.push_back(m1::adapt(record,l));fields.push_back(m1::segments(record,l));}
    if(!boundary){std::set<Bytes> selected;for(auto i:requested)selected.insert(raw[i]);require(selected.size()==alpha,"order-sensitive records must differ");}
    s4n::MemoryDB db(encoded,l);PIRParameters p{};p.d=1;p.alpha=1;p.n[0]=N;
    s4n::NativeReply reply(p,db,server);reply.importDataNFL(0,l.logical_bytes);
    require(db.reads==N && reply.blocks()==l.L && reply.computeReplySizeInChunks(l.logical_bytes)==l.L,"native importer/reply dimensions");
    s4n::check_import(server,reply.imported(),fields,l);
    s4n::check_backend(client,w);s4n::check_backend(server,w);
    const uint64_t ct=client.publicParams.getCiphertextBitsize()/8;
    uint64_t query_count=0,reply_count=0;std::vector<uint64_t> messages;
    for(unsigned i=0;i<N;++i){
        uint64_t message=0;for(unsigned r=0;r<alpha;++r)if(requested[r]==i)message=K[r];
        uint64_t before=rng_count;char* cipher=m1::encrypt_integer(client,message);
        require(rng_count==before+2 && rng_sizes[before]==4096*8 && rng_sizes[before+1]==4096*2*8,"native encryption randomness path");
        std::vector<char> wire(cipher,cipher+ct);char* received=static_cast<char*>(malloc(ct));require(received!=nullptr,"query allocation");
        memcpy(received,wire.data(),ct);require(memcmp(cipher,received,ct)==0,"ciphertext serialization loss");free(cipher);
        reply.pushQuery(received,ct,0,i);++query_count;messages.push_back(message);
    }
    require(query_count==N && rng_count==2+2*N,"exactly N direct encryptions, no extra ciphertexts");
    reply.evaluate();require(reply.repliesAmount==l.L,"one native reply per L block");
    std::vector<uint64_t> packed;std::vector<std::vector<uint64_t>> unpacked(alpha);
    for(uint64_t block=0;block<l.L;++block){
        std::vector<char> wire(reply.repliesArray[block],reply.repliesArray[block]+ct);
        require(memcmp(wire.data(),reply.repliesArray[block],ct)==0,"reply serialization loss");
        auto recovered=s4n::decrypt_fields(client,wire.data(),w);++reply_count;
        packed.insert(packed.end(),recovered.begin(),recovered.end());
        for(uint64_t y:recovered){auto digits=m1::unpack(y,l,alpha);for(unsigned r=0;r<alpha;++r)unpacked[r].push_back(digits[r]);}
    }
    uint64_t maximum=0,minimum=std::numeric_limits<uint64_t>::max(),boundary_hits=0,padding_checked=0;
    for(uint64_t j=0;j<l.L*l.n;++j){
        uint64_t expected=0;for(unsigned r=0;r<alpha;++r)expected+=K[r]*fields[requested[r]][j];
        require(expected<l.t() && packed[j]==expected,"every packed coefficient exact");
        for(unsigned r=0;r<alpha;++r)require(unpacked[r][j]==fields[requested[r]][j],"every unpacked segment exact");
        if(j>=l.J){require(packed[j]==0,"polynomial padding");++padding_checked;}
        if(packed[j]==l.t()-1)++boundary_hits;maximum=std::max(maximum,packed[j]);minimum=std::min(minimum,packed[j]);
    }
    if(boundary)require(boundary_hits>0 && maximum==l.t()-1,"encrypted t-1 boundary recovery");
    ptree digits;std::vector<std::string> decoded_hex,expected_hex;
    for(unsigned r=0;r<alpha;++r){
        Bytes decoded=m1::decode(unpacked[r],l);require(decoded==raw[requested[r]],"ordered full record decode");
        if(ell%8)require((decoded.back()>>(ell%8))==0,"unused raw byte padding");
        if(ell%rho)require((unpacked[r][l.J-1]>>(ell%rho))==0,"last digit cannot contaminate next slot");
        digits.push_back({"",b2_json_array(unpacked[r])});decoded_hex.push_back(hex(decoded.data(),decoded.size()));expected_hex.push_back(hex(raw[requested[r]].data(),raw[requested[r]].size()));
    }
    require(rng_count==2+2*N && reply_count==l.L,"no hidden extra encryption/decryption");
    s4n::check_backend(client,w);s4n::check_backend(server,w);
    ptree result;result.put("case_id",job.get<std::string>("case_id"));result.put("timing_label",label);result.put("timing_collected",false);
    result.put("alpha",alpha);result.put("rho_0",rho);result.put("w",w);result.put("N",N);result.put("ell_bits",ell);
    result.put("J",l.J);result.put("L",l.L);result.put("B",l.B());result.put("t",l.t());result.add_child("weights",b2_json_array(K));
    result.add_child("targets",b2_json_array(requested));result.add_child("query_messages",b2_json_array(messages));
    result.put("raw_DB_sha256",db_hash(raw));result.put("encoded_DB_sha256",db_hash(encoded));
    result.put("encoded_bytes_per_record",l.logical_bytes);result.put("fixture_seed",seed);result.put("boundary",boundary);result.put("order_mode",order);
    result.add_child("packed_coefficients",b2_json_array(packed));result.add_child("unpacked_segments",digits);
    result.add_child("decoded_records_hex",b2_json_array(decoded_hex));result.add_child("expected_records_hex",b2_json_array(expected_hex));
    result.put("coefficient_checks",packed.size());result.put("unpack_checks",packed.size()*alpha);result.put("record_checks",alpha);
    result.put("imported_residue_checks",uint64_t(N)*l.L*l.n*2);result.put("padding_coefficients_checked",padding_checked);
    result.put("minimum_packed_coefficient",minimum);result.put("maximum_packed_coefficient",maximum);result.put("t_minus_1_hits",boundary_hits);
    result.put("pid",getpid());result.put("fresh_client_key",true);result.put("key_fingerprint",key_fingerprint);
    result.put("client_key_generation_calls",1);result.put("server_unused_key_generation_calls",1);result.put("rng_calls",rng_count);
    result.put("query_ciphertexts",query_count);result.put("reply_ciphertexts",reply_count);result.put("native_reply_calls",1);
    result.put("native_decrypt_calls",reply_count);result.put("ciphertext_bytes",ct);result.put("n",4096);result.put("q",s4n::Q);result.put("Berr",200);
    result.put("sampler_label","native XPIR unchanged; not chi_r");result.put("direct_weight_encryption",true);result.put("no_extra_ciphertexts",true);
    result.put("serialization_lossless",true);result.put("integer_range_checks",true);result.put("padding_check",true);result.put("requested_order_exact",true);
    result.put("status","NATIVE_E2E_PASS");save(path,result);
}

int main(int argc,char** argv){
    try{
        require(sizeof(unsigned int)==4 && sizeof(uint64_t)==8,"pinned integer ABI");
        uint16_t endian=1;require(*reinterpret_cast<unsigned char*>(&endian)==1,"pinned little endian ABI");
        require(argc==3 || argc==4,"usage: b2_worker --probe result OR --case job result");
        if(std::string(argv[1])=="--probe" && argc==3){probe(argv[2]);return 0;}
        require(std::string(argv[1])=="--case" && argc==4,"invalid mode");
        ptree job;boost::property_tree::read_json(argv[2],job);run_case(job,argv[3]);return 0;
    }catch(const std::exception& error){
        std::cerr<<"B2_FUNCTIONAL_FAIL "<<error.what()<<std::endl;
        if(argc==4){ptree failure;failure.put("status","NATIVE_E2E_FAIL");failure.put("failure_reason",error.what());failure.put("timing_label","FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE");save(argv[3],failure);}
        return 1;
    }
}
