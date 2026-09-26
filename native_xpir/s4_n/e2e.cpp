// New S4-N cases only. No benchmark, estimator, production sampler, or bridge.
#include "support.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <iomanip>
using s4n::require;
struct RngCall {uint64_t nonce,bytes;};
static std::vector<RngCall> rng_calls;
extern "C" int __real_crypto_stream_salsa20_amd64_xmm6(unsigned char*,unsigned long long,const unsigned char*,const unsigned char*);
extern "C" int __wrap_crypto_stream_salsa20_amd64_xmm6(unsigned char* out,unsigned long long len,const unsigned char* nonce,const unsigned char* key) {
    uint64_t v=0;for(unsigned i=0;i<8;++i)v|=uint64_t(nonce[i])<<(8*i);
    if(!rng_calls.empty())require(v==rng_calls.back().nonce+1,"nonsequential Salsa20 nonce");
    rng_calls.push_back({v,len});
    return __real_crypto_stream_salsa20_amd64_xmm6(out,len,nonce,key);
}
static std::string quoted(const std::string& s) {
    std::string out="\"";
    for(char c:s) {if(c=='\\'||c=='"')out+='\\';if(c=='\n')out+="\\n";else out+=c;}
    return out+'"';
}
static std::string hex(const std::vector<unsigned char>& v) {
    std::ostringstream out;
    for(auto b:v)out<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(b);
    return out.str();
}
template<class T> static std::string json_array(const std::vector<T>& v) {
    std::ostringstream out;out<<'[';
    for(size_t i=0;i<v.size();++i){if(i)out<<',';out<<v[i];}out<<']';return out.str();
}
static std::string string_array(const std::vector<std::string>& v) {
    std::ostringstream out;out<<'[';
    for(size_t i=0;i<v.size();++i){if(i)out<<',';out<<quoted(v[i]);}out<<']';return out.str();
}
struct Case {
    std::string id,kind,data_class,group;
    unsigned N,rho,w;uint64_t ell;std::vector<unsigned> targets;
};
static std::vector<std::vector<unsigned char>> records(const Case& c) {
    std::vector<std::vector<unsigned char>> raw(c.N,std::vector<unsigned char>((c.ell+7)/8,0));
    uint64_t state=0x53444e0000000000ULL ^ c.ell ^ (uint64_t(c.rho)<<32) ^ (uint64_t(c.N)<<16);
    for(unsigned i=0;i<c.N;++i) {
        if(c.data_class=="equal_pseudorandom" && i>0){raw[i]=raw[0];continue;}
        for(uint64_t p=0;p<c.ell;++p) {
            unsigned b=0;
            if(c.data_class=="all_max")b=1;
            else if(c.data_class=="alternating")b=(i+p)%2;
            else if(c.data_class=="boundaries") {
                uint64_t values[]={0,1,(uint64_t(1)<<c.rho)-1};
                b=(values[(i+p/c.rho)%3]>>(p%c.rho))&1;
            } else if(c.data_class=="pseudorandom" || c.data_class=="equal_pseudorandom") {
                state^=state<<13;state^=state>>7;state^=state<<17;b=state&1;
            } else require(c.data_class=="all_zero","unknown fixture");
            m1::setbit(raw[i],p,b);
        }
    }
    return raw;
}
static void full_field_probe(unsigned w,std::ofstream& extra) {
    NFLlib lib;lib.setNewParameters(s4n::DEGREE,120);
    require(lib.getnbModuli()==2 && lib.getmoduli()[0]==s4n::P1 && lib.getmoduli()[1]==s4n::P2,"probe profile");
    // New no-encryption importer diagnostic: exercise all bits of t-1.
    std::vector<unsigned char> bytes(s4n::DEGREE*w/8+16,0);
    std::fill(bytes.begin(),bytes.begin()+s4n::DEGREE*w/8,255);
    unsigned char* input=bytes.data();uint64_t blocks=0;
    auto polys=lib.deserializeDataNFL(&input,1,uint64_t(s4n::DEGREE)*w,w,blocks);
    require(blocks==1,"full field block count");
    lib.invnttAndPowInvPhi(polys[0]);
    for(unsigned i=0;i<s4n::DEGREE*2;++i)
        require(polys[0][i]==(uint64_t(1)<<w)-1,"t-1 importer truncation");
    free(polys[0]);free(polys);
    extra<<"{\"kind\":\"full_field_import\",\"w\":"<<w<<",\"t\":"<<(uint64_t(1)<<w)
         <<",\"maximum\":"<<((uint64_t(1)<<w)-1)<<",\"status\":\"PASS\",\"encrypted\":false}\n";
}
static void rejects(std::ofstream& extra) {
    for(unsigned rho:{8u,12u,16u}) {
        m1::Layout l(257,rho,2*rho,s4n::DEGREE);
        for(unsigned kind=0;kind<8;++kind) {
            const char* names[]={"insufficient_width","duplicate_target","out_of_range_target",
                "malformed_layout","wrong_encoded_length","nonzero_field_high_padding",
                "nonzero_final_segment_padding","weight_API_range"};
            bool rejected=false;
            try {
                if(kind==0) {m1::Layout bad(257,rho,2*rho-1,s4n::DEGREE);m1::radix_weights(bad,2);}
                if(kind==1)s4n::validate_targets(7,{1,1});
                if(kind==2)s4n::validate_targets(7,{0,7});
                if(kind==3){auto bad=l;++bad.encoded_bits;s4n::validate_layout(bad);}
                if(kind==4)s4n::validate_encoded(std::vector<unsigned char>(l.logical_bytes-1),l);
                if(kind==5){std::vector<unsigned char> b(l.logical_bytes);m1::setbit(b,rho,1);s4n::validate_encoded(b,l);}
                if(kind==6){std::vector<uint64_t> x(l.L*l.n);x[l.J-1]=uint64_t(1)<<(l.ell%l.rho);m1::decode(x,l);}
                if(kind==7){m1::Layout fixture(257,16,56,s4n::DEGREE);m1::validate_weights(fixture,m1::radix_weights(fixture,3));}
            }catch(const std::runtime_error& e){
                rejected=true;extra<<"{\"kind\":\"rejection\",\"rho_0\":"<<rho<<",\"test\":"<<quoted(names[kind])
                    <<",\"status\":\"PASS\",\"reason\":"<<quoted(e.what())<<",\"encrypted\":false}\n";
            }
            require(rejected,"rejection guard silently accepted invalid fixture");
        }
    }
}
static void run_case(const Case& c,const std::string& run_id,std::ofstream& out,std::ofstream& extra) {
    m1::Layout l(c.ell,c.rho,c.w,s4n::DEGREE);
    s4n::validate_layout(l);s4n::validate_targets(c.N,c.targets);
    auto K=m1::radix_weights(l,c.targets.size());m1::validate_weights(l,K);
    const size_t rng_start=rng_calls.size();
    s4n::Hooks hooks;NFLLWE client,server;
    {
        s4n::Phase phase(hooks,"ConfigureServer");
        s4n::configure_and_keygen(server,c.w);
    }
    const size_t key_start=rng_calls.size();
    {
        s4n::Phase phase(hooks,"KeyGen");
        s4n::configure_and_keygen(client,c.w);
    }
    require(rng_calls.size()==key_start+1 && rng_calls[key_start].bytes==s4n::DEGREE*2*8,"fresh KeyGen RNG");
    std::vector<std::vector<unsigned char>> raw,encoded;
    std::vector<std::vector<uint64_t>> expected_fields;
    {
        s4n::Phase phase(hooks,"Encode");
        raw=records(c);
        for(const auto& r:raw){encoded.push_back(m1::adapt(r,l));expected_fields.push_back(m1::segments(r,l));}
    }
    if(c.data_class=="pseudorandom" || c.data_class=="alternating")
        if(c.targets.size()==2)require(raw[c.targets[0]]!=raw[c.targets[1]],"order-sensitive fixture not distinct");
    s4n::MemoryDB db(encoded,l);
    PIRParameters p{};p.d=1;p.alpha=1;p.n[0]=c.N;
    s4n::NativeReply reply(p,db,server);
    {
        s4n::Phase phase(hooks,"Import");
        reply.importDataNFL(0,l.logical_bytes);
    }
    require(db.reads==c.N && reply.blocks()==l.L,"native DB path not fully imported");
    require(reply.computeReplySizeInChunks(l.logical_bytes)==l.L,"reply size mismatch");
    s4n::check_backend(server,c.w);s4n::check_backend(client,c.w);
    s4n::check_import(server,reply.imported(),expected_fields,l);
    const uint64_t ciphertext_bytes=client.publicParams.getCiphertextBitsize()/8;
    uint64_t query_bytes=0,reply_bytes=0,max_error=0,max_y=0;
    std::vector<char*> actual_queries;std::vector<uint64_t> messages;
    const size_t query_rng_start=rng_calls.size();
    {
        s4n::Phase phase(hooks,"QueryGen");
        for(unsigned i=0;i<c.N;++i) {
            uint64_t value=0;
            for(size_t r=0;r<K.size();++r)if(c.targets[r]==i)value=K[r];
            const size_t before=rng_calls.size();
            char* encrypted=m1::encrypt_integer(client,value); // Direct encrypt(value), never value*Enc(1).
            require(rng_calls.size()==before+2 && rng_calls[before].bytes==s4n::DEGREE*8 &&
                    rng_calls[before+1].bytes==s4n::DEGREE*2*8,"fresh encryption RNG path");
            // Explicit tested native wire payload: a||b, RNS-major uint64 little endian.
            std::vector<char> wire(encrypted,encrypted+ciphertext_bytes);
            char* received=static_cast<char*>(malloc(wire.size()));
            require(received!=nullptr,"query wire allocation");
            std::memcpy(received,wire.data(),wire.size());
            require(std::memcmp(received,encrypted,wire.size())==0,"query wire mismatch");
            free(encrypted);query_bytes+=wire.size();
            actual_queries.push_back(received);messages.push_back(value);
            reply.pushQuery(received,ciphertext_bytes,0,i);
        }
    }
    // Diagnostic audit is OUTSIDE QueryGen and adds no ciphertexts or PRNG calls.
    for(unsigned i=0;i<c.N;++i)max_error=std::max(max_error,s4n::audit_query(client,actual_queries[i],messages[i],c.w));
    require(rng_calls.size()==query_rng_start+2*c.N,"unexpected diagnostic encryption");
    if(c.id.find("_case0")!=std::string::npos) {
        bool rejected=false;const size_t before=rng_calls.size();
        try{free(m1::encrypt_integer(client,uint64_t(UINT_MAX)+1));}
        catch(const std::runtime_error&){rejected=true;}
        require(rejected && rng_calls.size()==before,"API overflow was not rejected before native encryption");
        extra<<"{\"kind\":\"rejection\",\"case_id\":"<<quoted(c.id)<<",\"rho_0\":"<<c.rho
             <<",\"test\":\"actual_encrypt_API_overflow_guard\",\"status\":\"PASS\",\"encrypted\":false}\n";
    }
    {
        s4n::Phase phase(hooks,"ReplyGen");
        reply.evaluate();
    }
    require(reply.repliesAmount==l.L,"native response count");
    std::vector<std::vector<uint64_t>> recovered(K.size()),ys;
    std::vector<std::vector<unsigned char>> decoded;
    {
        s4n::Phase phase(hooks,"ReplyExt");
        for(uint64_t j=0;j<l.L;++j) {
            std::vector<char> wire(reply.repliesArray[j],reply.repliesArray[j]+ciphertext_bytes);
            reply_bytes+=wire.size();
            ys.push_back(s4n::decrypt_fields(client,wire.data(),c.w));
            for(auto y:ys.back()) {
                auto xs=m1::unpack(y,l,K.size());
                for(size_t r=0;r<K.size();++r)recovered[r].push_back(xs[r]);
            }
        }
        for(const auto& fields:recovered)decoded.push_back(m1::decode(fields,l));
    }
    for(uint64_t j=0;j<l.L;++j)for(unsigned u=0;u<l.n;++u) {
        uint64_t expected=0;
        for(size_t r=0;r<K.size();++r)expected+=K[r]*expected_fields[c.targets[r]][j*l.n+u];
        require(expected<l.t(),"B: expected packed coefficient overflow");
        require(ys[j][u]==expected,"C: decrypted packed coefficient mismatch");
        max_y=std::max(max_y,expected);
        for(size_t r=0;r<K.size();++r)
            require(recovered[r][j*l.n+u]==expected_fields[c.targets[r]][j*l.n+u],"D: unpacked segment mismatch");
    }
    std::vector<std::string> expected_hex,decoded_hex;
    for(size_t r=0;r<K.size();++r) {
        require(decoded[r]==raw[c.targets[r]],"E: ordered record mismatch");
        expected_hex.push_back(hex(raw[c.targets[r]]));decoded_hex.push_back(hex(decoded[r]));
    }
    s4n::check_backend(client,c.w);s4n::check_backend(server,c.w);
    require(rng_calls.size()==rng_start+2+2*c.N,"task has unexpected sampler calls");
    require(query_bytes==c.N*ciphertext_bytes && reply_bytes==l.L*ciphertext_bytes,"wire accounting");
    out<<"{\"case_id\":"<<quoted(c.id)<<",\"run_id\":"<<quoted(run_id)
       <<",\"key_id\":"<<quoted(run_id+"/"+c.id+"/client")<<",\"kind\":"<<quoted(c.kind)
       <<",\"baseline_group\":"<<quoted(c.group)<<",\"config_id\":"<<quoted("n4096_Q2_rho"+std::to_string(c.rho)+"_w"+std::to_string(c.w))
       <<",\"N\":"<<c.N<<",\"ell\":"<<c.ell<<",\"rho_0\":"<<c.rho<<",\"w\":"<<c.w
       <<",\"B\":"<<l.B()<<",\"t\":"<<l.t()<<",\"K\":"<<json_array(K)<<",\"alpha\":"<<K.size()
       <<",\"n\":4096,\"q_id\":\"Q2\",\"q\":"<<quoted(s4n::Q)
       <<",\"primes\":[2305843009213317121,2305843009213120513],\"recursion_dimension\":1,\"aggregation_factor\":1"
       <<",\"targets\":"<<json_array(c.targets)<<",\"index_base\":0,\"data_class\":"<<quoted(c.data_class)
       <<",\"J\":"<<l.J<<",\"L\":"<<l.L<<",\"encoded_bits\":"<<l.encoded_bits<<",\"encoded_bytes_per_record\":"<<l.logical_bytes
       <<",\"full_field_import_probe\":\"PASS\",\"import_check\":\"PASS\",\"packed_coefficient_check\":\"PASS\""
       <<",\"decrypt_check\":\"PASS\",\"unpack_check\":\"PASS\",\"record_check\":\"PASS\",\"order_check\":\"PASS\""
       <<",\"width_check\":\"PASS\",\"cache_lifecycle\":\"fresh objects and import per task; no reuse\""
       <<",\"incomplete_final_segment\":"<<(c.ell%c.rho?"true":"false")<<",\"padding_check\":\"PASS\""
       <<",\"fresh_key\":true,\"key_generation_calls\":1,\"server_unused_key_generation_calls\":1"
       <<",\"query_encrypt_calls\":"<<c.N<<",\"query_rng_calls\":"<<2*c.N
       <<",\"native_reply_calls\":1,\"native_decrypt_calls\":"<<l.L
       <<",\"key_rng_nonce\":"<<rng_calls[key_start].nonce<<",\"first_query_rng_nonce\":"<<rng_calls[query_rng_start].nonce
       <<",\"last_query_rng_nonce\":"<<rng_calls.back().nonce<<",\"no_extra_ciphertexts\":true"
       <<",\"noise_Berr\":200,\"observed_max_query_error\":"<<max_error<<",\"noise_scope\":\"engineering diagnostic only\""
       <<",\"max_expected_packed_coefficient\":"<<max_y<<",\"max_decrypted_packed_coefficient\":"<<max_y
       <<",\"ciphertext_bytes\":"<<ciphertext_bytes<<",\"query_payload_bytes\":"<<query_bytes<<",\"reply_payload_bytes\":"<<reply_bytes
       <<",\"byte_scope\":\"actual copied native payload; no transport framing\",\"phase_events\":"<<string_array(hooks.events)
       <<",\"timing_collected\":false,\"expected_records_hex\":"<<string_array(expected_hex)
       <<",\"decoded_records_hex\":"<<string_array(decoded_hex)
       <<",\"status\":\"NATIVE_E2E_PASS\",\"failure_reason\":null}\n";
    out.flush();
    std::cout<<"S4N_E2E_PASS "<<c.id<<" ordered_bit_perfect=1 fresh_key_retired_at_return=1\n";
}
static std::vector<Case> plan() {
    std::vector<Case> cases;
    for(unsigned rho:{8u,12u,16u}) {
        for(uint64_t ell:{256ULL,512ULL,1024ULL,2048ULL})for(unsigned N:{7u,32u}) {
            std::vector<std::vector<unsigned>> tuples={{0,N-1},{N-1,0},{0,1},{1,0},{0,N-1},{N-1,0},
                                                       {1,N-2},{N-2,1},{N-2,N-1},{N-1,N-2}};
            const char* classes[]={"all_zero","all_max","alternating","alternating","pseudorandom","pseudorandom",
                                   "boundaries","boundaries","equal_pseudorandom","equal_pseudorandom"};
            for(unsigned z=0;z<10;++z)
                cases.push_back({"packed_rho"+std::to_string(rho)+"_ell"+std::to_string(ell)+"_N"+std::to_string(N)+"_case"+std::to_string(z),
                                 "main_packed",classes[z],"",N,rho,2*rho,ell,tuples[z]});
        }
        for(unsigned z=0;z<2;++z)
            cases.push_back({"packed_rho"+std::to_string(rho)+"_ell257_N7_padding"+std::to_string(z),
                             "main_packed","pseudorandom","",7,rho,2*rho,257,z?std::vector<unsigned>{6,0}:std::vector<unsigned>{0,6}});
        for(unsigned N:{7u,32u})for(unsigned z=0;z<2;++z) {
            std::string group="baseline_rho"+std::to_string(rho)+"_N"+std::to_string(N);
            cases.push_back({group+"_record"+std::to_string(z),"baseline_single","pseudorandom",group,
                             N,rho,2*rho,1024,{z?N-1:0}});
        }
    }
    return cases;
}
int main(int argc,char** argv) {
    try {
        require(argc==4,"usage: s4_n_e2e cases.jsonl extra.jsonl run_id");
        require(sizeof(unsigned int)*CHAR_BIT==32 && sizeof(uint64_t)==8,"x86-64 message ABI");
        uint16_t endian=1;require(*reinterpret_cast<unsigned char*>(&endian)==1,"little endian required");
        std::ofstream out(argv[1]),extra(argv[2]);require(bool(out)&&bool(extra),"log open");
        require(s4n::peak_memory_hook_available(),"getrusage peak-memory hook unavailable");
        std::cout<<"S4N pinned=75c5e912cbe6a8d5bf5ac0f3f74a665b0265c78c n=4096 Q2 only\n"
                 <<"NO_BENCHMARK; upstream diagnostic timer lines are incidental and are not compared\n"
                 <<"RNG observer forwards unchanged Salsa20 seeded by /dev/urandom; no seed override\n";
        for(unsigned w:{16u,24u,32u})full_field_probe(w,extra);
        rejects(extra);
        unsigned pass=0,failed=0;
        for(const auto& c:plan()) {
            try{run_case(c,argv[3],out,extra);++pass;}
            catch(const std::exception& e) {
                ++failed;
                out<<"{\"case_id\":"<<quoted(c.id)<<",\"run_id\":"<<quoted(argv[3])<<",\"rho_0\":"<<c.rho
                   <<",\"w\":"<<c.w<<",\"kind\":"<<quoted(c.kind)<<",\"status\":\"NATIVE_E2E_FAIL\",\"failure_reason\":"<<quoted(e.what())<<"}\n";
                out.flush();std::cerr<<"S4N_FAIL "<<c.id<<' '<<e.what()<<'\n';
            }
        }
        extra<<"{\"kind\":\"summary\",\"cases\":"<<plan().size()<<",\"pass\":"<<pass<<",\"fail\":"<<failed
             <<",\"rng_calls\":"<<rng_calls.size()<<",\"production_style_randomness\":true"
             <<",\"seed_override\":false,\"peak_memory_hook_available\":true,\"timing_collected\":false}\n";
        std::cout<<"S4N_SUMMARY pass="<<pass<<" fail="<<failed<<" NO_PERFORMANCE_RESULTS\n";
        return failed?1:0;
    }catch(const std::exception& e){std::cerr<<"S4N_HARNESS_ERROR "<<e.what()<<'\n';return 2;}
}
