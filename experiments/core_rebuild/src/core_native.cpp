// SPDX-License-Identifier: GPL-3.0-or-later
// Fresh-exec query runner and single-owner preprocessing for the core rebuild.
#include "core_native.hpp"
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <openssl/sha.h>
#include <sys/resource.h>
#include <sched.h>
#include <time.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>

using namespace core_rebuild;
using boost::property_tree::ptree;
namespace {
uint64_t rng_calls=0, rng_last=0, rng_key_size_calls=0;
bool rng_sequence=true;
uint64_t now_ns() {
    timespec t{}; require(clock_gettime(CLOCK_MONOTONIC_RAW,&t)==0,"monotonic clock unavailable");
    return uint64_t(t.tv_sec)*1000000000+uint64_t(t.tv_nsec);
}
uint64_t cpu_ns(const timeval& t) { return uint64_t(t.tv_sec)*1000000000+uint64_t(t.tv_usec)*1000; }
struct Cpu { uint64_t user,system; };
Cpu self_cpu() {
    rusage r{};require(getrusage(RUSAGE_SELF,&r)==0,"process CPU accounting unavailable");
    return {cpu_ns(r.ru_utime),cpu_ns(r.ru_stime)};
}
std::string hex(const unsigned char* b,size_t size) {
    std::ostringstream s;s<<std::hex<<std::setfill('0');
    for(size_t i=0;i<size;++i)s<<std::setw(2)<<unsigned(b[i]);return s.str();
}
std::string digest(const void* memory,size_t count) {
    unsigned char out[SHA256_DIGEST_LENGTH];SHA256(static_cast<const unsigned char*>(memory),count,out);
    return hex(out,sizeof(out));
}
std::string database_digest(const Database& db) {
    SHA256_CTX context;SHA256_Init(&context);
    for (const auto& row:db)SHA256_Update(&context,row.data(),row.size());
    unsigned char out[32];SHA256_Final(out,&context);return hex(out,sizeof(out));
}
struct Phase {
    ptree& durations; ptree& events;std::string name;uint64_t begin;
    Phase(ptree& d,ptree& e,const std::string& n) : durations(d),events(e),name(n),begin(now_ns()) {}
    ~Phase() { const uint64_t end=now_ns();durations.put(name,end-begin);ptree p;p.put("begin",begin);p.put("end",end);events.add_child(name,p); }
};
struct Gate {
    int ready,go,data;
    explicit Gate(const ptree& job) : ready(job.get<int>("ready_fd",-1)),go(job.get<int>("go_fd",-1)),data(job.get<int>("data_fd",-1)) {
        require((ready>=0)==(go>=0),"incomplete barrier descriptor pair");
    }
    void start() const {
        if(ready<0)return;
        char r='R';transfer(ready,&r,1,true);char g=0;transfer(go,&g,1,false);require(g=='G',"invalid start gate");
    }
    void done() const { if(ready>=0){char d='D';transfer(ready,&d,1,true);} }
    void validate() const { if(go>=0){char v=0;transfer(go,&v,1,false);require(v=='V',"invalid validation gate");} }
};
Database read_fixture(const ptree& job,uint64_t N,const Layout& layout) {
    const std::string path=job.get<std::string>("raw_path",job.get<std::string>("fixture_path",""));
    if(path.empty())return fixture(N,layout,job.get<uint64_t>("fixture_seed"),job.get<std::string>("fixture_kind","pseudorandom"));
    int fd=::open(path.c_str(),O_RDONLY);require(fd>=0,"cannot open public fixture");
    try {
        struct stat info{};require(::fstat(fd,&info)==0 && uint64_t(info.st_size)==checked_product(N,layout.record_bytes),"public fixture byte count mismatch");
        Database result(N,Bytes(layout.record_bytes));
        for(auto& row:result) {
            transfer(fd,row.data(),row.size(),false);
            if(layout.ell%8)require((row.back()>>(layout.ell%8))==0,"public fixture unused bits nonzero");
        }
        ::close(fd);return result;
    }catch(...){::close(fd);throw;}
}
Database read_expected_targets(const ptree& job,uint64_t N,const Layout& layout,const std::vector<unsigned>& targets) {
    const std::string path=job.get<std::string>("raw_path",job.get<std::string>("fixture_path",""));
    if(path.empty()) {
        const auto raw=read_fixture(job,N,layout);Database selected;
        for(unsigned target:targets)selected.push_back(raw[target]);return selected;
    }
    int fd=::open(path.c_str(),O_RDONLY);require(fd>=0,"cannot open target-validation fixture");
    try {
        struct stat info{};require(::fstat(fd,&info)==0 && uint64_t(info.st_size)==checked_product(N,layout.record_bytes),"public fixture byte count mismatch");
        Database selected(targets.size(),Bytes(layout.record_bytes));
        for(size_t k=0;k<targets.size();++k) {
            require(::lseek(fd,checked_product(targets[k],layout.record_bytes),SEEK_SET)>=0,"cannot position target-validation fixture");
            transfer(fd,selected[k].data(),selected[k].size(),false);
            if(layout.ell%8)require((selected[k].back()>>(layout.ell%8))==0,"public fixture unused bits nonzero");
        }
        ::close(fd);return selected;
    }catch(...){::close(fd);throw;}
}
void metadata(ptree& result,uint64_t N,const Layout& layout) {
    result.put("schema","CORE_NATIVE_V1");result.put("pid",getpid());result.put("ppid",getppid());
    result.put("N",N);result.put("ell_bits",layout.ell);result.put("rho_0",layout.rho);
    result.put("n",DEGREE);result.put("w",WIDTH);result.put("t",uint64_t(1)<<WIDTH);
    result.put("q",MODULUS);result.put("prime_1",P1);result.put("prime_2",P2);
    result.put("J",layout.J);result.put("L",layout.L);result.put("native_error_upper_bound",ERROR_MAX);
    result.put("ciphertext_buffer_bytes",CIPHER_BYTES);result.put("omp_max_threads",omp_get_max_threads());
    result.put("rng_calls",rng_calls);result.put("rng_nonce_sequence",rng_sequence);
    result.put("clock","CLOCK_MONOTONIC_RAW");
    cpu_set_t cpus;CPU_ZERO(&cpus);require(sched_getaffinity(0,sizeof(cpus),&cpus)==0,"cannot read affinity");
    ptree affinity;for(int i=0;i<CPU_SETSIZE;++i)if(CPU_ISSET(i,&cpus)){ptree p;p.put("",i);affinity.push_back({"",p});}result.add_child("cpu_affinity",affinity);
}
std::vector<uint64_t> read_fields(const unsigned char* p) {
    std::vector<uint64_t> fields(DEGREE,0);
    for(uint64_t i=0;i<DEGREE;++i)
        for(uint64_t bit=0;bit<WIDTH;++bit)fields[i]|=uint64_t((p[(i*WIDTH+bit)/8]>>((i*WIDTH+bit)%8))&1)<<bit;
    return fields;
}
uint64_t check_actual_error(NFLLWE& client,char* ciphertext,uint64_t message) {
    const auto* words=reinterpret_cast<const uint64_t*>(ciphertext);
    std::vector<uint64_t> residues(DEGREE*2),first(DEGREE);
    for(unsigned m=0;m<2;++m)for(uint64_t i=0;i<DEGREE;++i) {
        const uint64_t prime=client.getmoduli()[m];
        const uint64_t product=static_cast<__uint128_t>(words[m*DEGREE+i])*client.getsecretKey()[m][i]%prime;
        residues[m*DEGREE+i]=(words[2*DEGREE+m*DEGREE+i]+prime-product)%prime;
    }
    client.getnflInstance().invnttAndPowInvPhi(residues.data());
    uint64_t maximum=0;
    for(unsigned m=0;m<2;++m) {
        mpz_class prime(client.getmoduli()[m]),t=mpz_class(1)<<WIDTH,inverse;
        require(mpz_invert(inverse.get_mpz_t(),t.get_mpz_t(),prime.get_mpz_t())!=0,"noise amplifier inverse unavailable");
        const uint64_t inv=inverse.get_ui(),p=client.getmoduli()[m];
        for(uint64_t i=0;i<DEGREE;++i) {
            const uint64_t plaintext=i?0:message;
            const uint64_t e=static_cast<__uint128_t>((residues[m*DEGREE+i]+p-plaintext)%p)*inv%p;
            require(e<=ERROR_MAX,"actual query error outside source-supported integer range");
            if(!m)first[i]=e;else require(first[i]==e,"CRT errors differ");
            maximum=std::max(maximum,e);
        }
    }
    return maximum;
}
void prepare(const ptree& job,ptree& result) {
    const uint64_t N=job.get<uint64_t>("N");Layout layout(job.get<uint64_t>("ell_bits"),job.get<uint64_t>("rho_0"));
    require(N && N<=UINT32_MAX && job.get<uint64_t>("w",WIDTH)==WIDTH,"prepare domain");
    const uint64_t seed=job.get<uint64_t>("fixture_seed");Gate gate(job);
    // Public fixture loading/generation and hashing precede READY. Neither operation creates secret state.
    Database raw=read_fixture(job,N,layout);
    const std::string raw_digest=database_digest(raw);
    gate.start();Cpu cpu_before=self_cpu();const uint64_t begin=now_ns();ptree phases,events;
    std::unique_ptr<NFLLWE> server;
    {Phase phase(phases,events,"ConfigureImportBackend");server.reset(new NFLLWE);configure_key(*server);}
    Database encoded;
    {Phase phase(phases,events,"EncodeDatabase");encoded.reserve(N);for(const auto& row:raw)encoded.push_back(layout.encode(row));}
    PIRParameters params{};params.d=1;params.alpha=1;params.n[0]=N;
    std::unique_ptr<MemoryDatabase> db(new MemoryDatabase(std::move(encoded)));std::unique_ptr<ImportedOwnerReply> owner;
    {Phase phase(phases,events,"ImportDatabase");owner.reset(new ImportedOwnerReply(params,*db,*server));owner->importDataNFL(0,layout.field_bytes);require(owner->blocks()==layout.L,"actual imported block count mismatch");}
    {Phase phase(phases,events,"ConstructSharedData");export_mapping(job.get<std::string>("shared_path"),owner->imported(),N,layout,seed,job.get<int>("db_fd",-1));}
    {Phase phase(phases,events,"ReleaseImportOwner");owner.reset();db.reset();server.reset();Database empty;raw.swap(empty);}
    gate.done();const uint64_t end=now_ns();const Cpu cpu_after=self_cpu();gate.validate();
    result.put("role","prepare");result.put("status","COMPLETE");result.put("preprocess_start_ns",begin);result.put("preprocess_end_ns",end);result.put("preprocess_total_ns",end-begin);
    result.put("cpu_user_ns",cpu_after.user-cpu_before.user);result.put("cpu_system_ns",cpu_after.system-cpu_before.system);
    result.put("imported_data_bytes",imported_bytes(N,layout));result.put("mapping_bytes",DATA_OFFSET+imported_bytes(N,layout));
    result.put("fixture_sha256",raw_digest);result.put("import_backend_unused_key_generation_calls",1);result.put("import_calls",1);result.put("native_import_owner_released_before_done",true);
    result.add_child("phase_ns",phases);result.add_child("phase_events",events);metadata(result,N,layout);
}
void query(const ptree& job,ptree& result) {
    const uint64_t N=job.get<uint64_t>("N");Layout layout(job.get<uint64_t>("ell_bits"),job.get<uint64_t>("rho_0"));
    require(N && N<=UINT32_MAX && job.get<uint64_t>("w",WIDTH)==WIDTH,"query domain");
    std::vector<unsigned> targets;
    for(auto& entry:job.get_child("targets")) {
        const unsigned index=entry.second.get_value<unsigned>();require(index<N,"target out of range");
        require(std::find(targets.begin(),targets.end(),index)==targets.end(),"duplicate ordered target");targets.push_back(index);
    }
    const auto weights=layout.weights(targets.size());sufficient_screen(N,layout,targets.size());
    const uint64_t seed=job.get<uint64_t>("fixture_seed");Gate gate(job);
    const Database expected_records=read_expected_targets(job,N,layout,targets);
    require(rng_calls==0,"query RNG initialized before timed start");gate.start();
    Cpu cpu_before=self_cpu();const uint64_t begin=now_ns();ptree phases,events;
    std::unique_ptr<ReadOnlyMapping> mapping;
    {Phase phase(phases,events,"BorrowSharedData");mapping.reset(new ReadOnlyMapping(job.get<std::string>("shared_path"),N,layout,seed));}
    std::unique_ptr<NFLLWE> client;
    const uint64_t key_rng_before=rng_calls;
    {Phase phase(phases,events,"ClientSetupKeyGen");client.reset(new NFLLWE);configure_key(*client);}
    const uint64_t key_rng_after=rng_calls;
    PIRParameters params{};params.d=1;params.alpha=1;params.n[0]=N;
    std::unique_ptr<BorrowedReply> reply;
    std::vector<uint64_t> messages(N,0);for(size_t i=0;i<targets.size();++i)messages[targets[i]]=weights[i];
    std::vector<char*> ciphertexts;ciphertexts.reserve(N);
    uint64_t query_bytes=0,reply_bytes=0;
    const uint64_t query_rng_before=rng_calls;
    {Phase phase(phases,events,"QueryGen");reply.reset(new BorrowedReply(params,*client,*mapping));
        for(uint64_t i=0;i<N;++i) {
            require(messages[i]<=UINT32_MAX && messages[i]<layout.t(),"query message cannot be represented exactly");
            char* encrypted=client->encrypt(static_cast<unsigned>(messages[i]),1);
            require(encrypted,"native encryption returned null");ciphertexts.push_back(encrypted);
            query_bytes+=client->publicParams.getCiphertextBitsize()/8;
            reply->pushQuery(encrypted,client->publicParams.getCiphertextBitsize()/8,0,i);
        }
    }
    const uint64_t query_rng_after=rng_calls;
    {Phase phase(phases,events,"ReplyGen");reply->evaluate();}
    std::vector<uint64_t> actual_fields;actual_fields.reserve(layout.fields());
    std::vector<std::vector<uint64_t>> segments(targets.size());for(auto& x:segments)x.reserve(layout.fields());
    Database decoded(targets.size(),Bytes(layout.record_bytes,0));
    {Phase phase(phases,events,"ReplyExt");
        for(uint64_t b=0;b<layout.L;++b) {
            const size_t bytes=client->publicParams.getCiphertextBitsize()/8;reply_bytes+=bytes;
            unsigned char* plain=reinterpret_cast<unsigned char*>(client->decrypt(reply->repliesArray[b],1,bytes,DEGREE*WIDTH/8));
            require(plain,"native decryption returned null");const auto values=read_fields(plain);std::free(plain);
            actual_fields.insert(actual_fields.end(),values.begin(),values.end());
            for(uint64_t y:values)for(size_t k=0;k<targets.size();++k)segments[k].push_back((y/weights[k])%layout.B());
        }
        for(size_t k=0;k<targets.size();++k)for(uint64_t bit=0;bit<layout.ell;++bit)
            decoded[k][bit/8] |= ((segments[k][bit/layout.rho]>>(bit%layout.rho))&1) << (bit%8);
    }
    {Phase phase(phases,events,"CollectRecords");if(gate.data>=0)for(auto& row:decoded)transfer(gate.data,row.data(),row.size(),true);}
    gate.done();const uint64_t end=now_ns();const Cpu cpu_after=self_cpu();gate.validate();
    // No result validation, hashing, audit or JSON-file writing competes with another timed query.
    bool correct=true;
    std::vector<std::vector<uint64_t>> expected;for(const auto& row:expected_records)expected.push_back(layout.segments(row));
    for(uint64_t j=0;j<layout.fields();++j) {
        uint64_t packed=0;
        for(size_t k=0;k<targets.size();++k){packed+=weights[k]*expected[k][j];correct &= segments[k][j]==expected[k][j];}
        correct &= actual_fields[j]==packed && actual_fields[j]<layout.t();
    }
    for(size_t k=0;k<targets.size();++k){correct &= layout.decode(segments[k])==decoded[k];correct &= decoded[k]==expected_records[k];}
    require(key_rng_after-key_rng_before==1 && query_rng_after-query_rng_before==2*N && rng_calls==1+2*N && rng_sequence,"native fresh RNG call path mismatch");
    require(query_bytes==N*CIPHER_BYTES && reply_bytes==layout.L*CIPHER_BYTES,"actual ciphertext buffer counts mismatch");
    uint64_t observed_error_max=0;
    if(job.get<bool>("audit_errors",false))for(uint64_t i=0;i<N;++i)observed_error_max=std::max(observed_error_max,check_actual_error(*client,ciphertexts[i],messages[i]));
    result.put("role","query");result.put("status",correct?"COMPLETE":"WRONG_OUTPUT");result.put("output_verified",correct);
    result.put("task_start_ns",begin);result.put("task_end_ns",end);result.put("task_total_ns",end-begin);
    result.put("cpu_user_ns",cpu_after.user-cpu_before.user);result.put("cpu_system_ns",cpu_after.system-cpu_before.system);
    result.put("request_alpha",targets.size());result.put("key_generation_calls",1);result.put("query_encrypt_calls",N);
    result.put("key_rng_calls",key_rng_after-key_rng_before);result.put("query_rng_calls",query_rng_after-query_rng_before);
    result.put("query_ciphertexts",N);result.put("reply_ciphertexts",layout.L);
    result.put("query_buffer_bytes",query_bytes);result.put("reply_buffer_bytes",reply_bytes);
    result.put("collected_record_bytes",targets.size()*layout.record_bytes);result.put("direct_weight_encryption",true);
    result.put("mapping_read_only",true);result.put("private_import_calls",0);result.put("validation_after_gate",true);
    result.put("all_coefficients_exact",correct);result.put("all_segments_exact",correct);result.put("padding_exact",correct);
    result.put("coefficient_checks",layout.fields());result.put("record_checks",targets.size());result.put("fixture_sha256",job.get<std::string>("fixture_sha256","not-provided"));
    result.put("audit_error_queries",job.get<bool>("audit_errors",false)?N:0);result.put("observed_error_max",observed_error_max);
    if(job.get<bool>("audit",true)) {
        result.put("first_ciphertext_fingerprint",digest(ciphertexts[0],CIPHER_BYTES));
    }
    ptree target_array,record_hashes;
    for(size_t k=0;k<targets.size();++k){ptree t,h;t.put("",targets[k]);h.put("",digest(decoded[k].data(),decoded[k].size()));target_array.push_back({"",t});record_hashes.push_back({"",h});}
    result.add_child("targets",target_array);result.add_child("record_sha256",record_hashes);result.add_child("phase_ns",phases);result.add_child("phase_events",events);metadata(result,N,layout);
}
}
extern "C" int __real_crypto_stream_salsa20_amd64_xmm6(unsigned char*,unsigned long long,const unsigned char*,const unsigned char*);
extern "C" int __wrap_crypto_stream_salsa20_amd64_xmm6(unsigned char* out,unsigned long long n,const unsigned char* nonce,const unsigned char* key) {
    uint64_t value=0;for(unsigned i=0;i<8;++i)value|=uint64_t(nonce[i])<<(8*i);
    if(rng_calls && value!=rng_last+1)rng_sequence=false;
    if(!rng_calls && value!=0)rng_sequence=false;
    rng_last=value;++rng_calls;if(n==DEGREE*2*sizeof(uint64_t))++rng_key_size_calls;
    return __real_crypto_stream_salsa20_amd64_xmm6(out,n,nonce,key);
}
int main(int argc,char** argv) {
    ptree result;
    try {
        require(argc==4,"usage: core_native prepare|query JOB.json OUTPUT.json");ptree job;read_json(argv[2],job);
        const int threads=job.get<int>("threads",1);require(threads>=1 && threads<=4,"reply thread budget");omp_set_dynamic(0);omp_set_num_threads(threads);
        const std::string role=argv[1];if(role=="prepare")prepare(job,result);else if(role=="query")query(job,result);else throw std::runtime_error("unknown native role");
        write_json(argv[3],result);return result.get<std::string>("status")=="COMPLETE"?0:20;
    }catch(const std::exception& error) {
        result.put("status","FAILED");result.put("failure_reason",error.what());
        if(argc==4){try{write_json(argv[3],result);}catch(...){}}
        std::cerr<<"core_native: "<<error.what()<<'\n';return 21;
    }
}
