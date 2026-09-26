// B0 measurement adapter. Validation and formatting run after task_end.
#include "crypto/NFLLWE.hpp"
#include "pir/replyGenerator/PIRReplyGeneratorNFL_internal.hpp"
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <openssl/sha.h>
#include <sys/resource.h>
#include <sched.h>
#include <unistd.h>
#include <time.h>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <memory>
#include <cstring>
#include <stdexcept>
#include <vector>
using Bytes=std::vector<unsigned char>;
using DB=std::vector<Bytes>;
using boost::property_tree::ptree;
constexpr uint64_t CT=131072, DEG=4096, SEED=0x42305f4441544131ULL;
uint64_t rng_calls=0,rng_last=0,rng_key_calls=0; bool rng_sequence=true;
extern "C" int __real_crypto_stream_salsa20_amd64_xmm6(unsigned char*,unsigned long long,const unsigned char*,const unsigned char*);
extern "C" int __wrap_crypto_stream_salsa20_amd64_xmm6(unsigned char* o,unsigned long long n,const unsigned char* nonce,const unsigned char* key){
    uint64_t v=0;for(unsigned i=0;i<8;i++)v|=uint64_t(nonce[i])<<(8*i);
    if(rng_calls && v!=rng_last+1)rng_sequence=false;
    rng_last=v; ++rng_calls; if(n==65536)++rng_key_calls;
    return __real_crypto_stream_salsa20_amd64_xmm6(o,n,nonce,key);
}
uint64_t now(){timespec t;clock_gettime(CLOCK_MONOTONIC_RAW,&t);return uint64_t(t.tv_sec)*1000000000+t.tv_nsec;}
uint64_t cpu(const timeval& t){return uint64_t(t.tv_sec)*1000000000+uint64_t(t.tv_usec)*1000;}
struct Span{uint64_t begin=0,end=0;};
enum {CONFIG,KEY,SERVER,ENCODE,IMPORT,QUERY,REPLY,EXTRACT,VALIDATE,COUNT};
const char* names[]={"ConfigureClient","ClientSetupKeyGen","ConfigureServer","EncodeDB","ImportPreprocess","QueryGen","ReplyGen","ReplyExt","ValidationOverhead"};
struct Timer{Span& s;Timer(Span& x):s(x){s.begin=now();}~Timer(){s.end=now();}};
uint64_t splitmix(uint64_t& state){
    uint64_t z=(state+=0x9e3779b97f4a7c15ULL);
    z=(z^(z>>30))*0xbf58476d1ce4e5b9ULL;z=(z^(z>>27))*0x94d049bb133111ebULL;return z^(z>>31);
}
DB fixture(unsigned N,unsigned ell){
    DB r(N,Bytes((ell+7)/8));uint64_t state=SEED ^ (uint64_t(N)<<32) ^ ell;
    for(auto& row:r)for(size_t b=0;b<row.size();b+=8){
        uint64_t z=splitmix(state);
        for(unsigned k=0;k<8 && b+k<row.size();k++)row[b+k]=(z>>(8*k))&255;
    }
    if(ell%8)for(auto& row:r)row.back()&=(1u<<(ell%8))-1;
    return r;
}
std::string hex(const unsigned char* p,size_t n){
    std::ostringstream o;for(size_t i=0;i<n;i++)o<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(p[i]);return o.str();
}
std::string digest(const DB& db){
    SHA256_CTX c;SHA256_Init(&c);for(const auto& r:db)SHA256_Update(&c,r.data(),r.size());
    unsigned char out[32];SHA256_Final(out,&c);return hex(out,32);
}
struct MemoryDB:DBHandler{
    DB data;std::vector<uint64_t> offsets;uint64_t reads=0;
    explicit MemoryDB(DB&& d):data(std::move(d)),offsets(data.size()){}
    std::string getCatalog(bool)override{return "B0 frozen fixture";}
    uint64_t getNbStream()override{return data.size();}
    uint64_t getmaxFileBytesize()override{return data[0].size();}
    bool openStream(uint64_t i,uint64_t o)override{offsets[i]=o;return true;}
    uint64_t readStream(uint64_t i,char* p,uint64_t n)override{memcpy(p,data[i].data()+offsets[i],n);offsets[i]+=n;++reads;return n;}
    void closeStream(uint64_t)override{}
};
struct NativeReply:PIRReplyGeneratorNFL_internal{
    NativeReply(PIRParameters& p,MemoryDB& db,NFLLWE& s):PIRReplyGeneratorNFL_internal(p,&db){
        mutex.unlock();setCryptoMethod(&s); // Do not call legacy setPirParams (overwrites w).
    }
    uint64_t blocks(){return currentMaxNbPolys;}
    void evaluate(){repliesAmount=currentMaxNbPolys;repliesIndex=0;generateReply();}
    ~NativeReply(){
        if(input_data){for(unsigned i=0;i<pirParam.n[0];i++){free(input_data[i].p[0]);free(input_data[i].p);}
            free(input_data);input_data=nullptr;}
    }
};
void setup(NFLLWE& c,unsigned w){c.setNewParameters(DEG,120,w);c.publicParams.setnoiseUB(200);c.recomputeNoiseAmplifiers();}
void require(bool p,const char* s){if(!p)throw std::runtime_error(s);}
void transfer(int fd,void* data,size_t n,bool writing){
    auto p=static_cast<char*>(data);while(n){ssize_t k=writing?write(fd,p,n):read(fd,p,n);require(k>0,"barrier pipe");p+=k;n-=k;}
}
int main(int argc,char** argv){
    try{
        require(argc==3,"worker JOB OUTPUT");ptree job;read_json(argv[1],job);
        unsigned N=job.get<unsigned>("N"),ell=job.get<unsigned>("ell_bits"),rho=job.get<unsigned>("rho_0"),w=2*rho;
        require(N>=2 && ell>0 && ell<=2048 && (rho==8||rho==12||rho==16),"preflight domain");
        std::vector<unsigned> targets;for(auto& v:job.get_child("targets"))targets.push_back(v.second.get_value<unsigned>());
        require(targets.size()==1||targets.size()==2,"alpha");for(auto i:targets)require(i<N,"target range");
        require(targets.size()==1||targets[0]!=targets[1],"distinct targets");
        auto raw=fixture(N,ell);const uint64_t J=(ell+rho-1)/rho,L=(J+DEG-1)/DEG,logical=L*DEG*w/8;
        std::vector<unsigned> messages(N);for(size_t k=0;k<targets.size();k++)messages[targets[k]]=uint64_t(1)<<(rho*k);
        Span spans[COUNT],prep;DB encoded,decoded;std::unique_ptr<NFLLWE> client,server;
        std::unique_ptr<MemoryDB> db;std::unique_ptr<NativeReply> reply;
        PIRParameters p{};p.d=1;p.alpha=1;p.n[0]=N;
        auto preprocess=[&](){
            prep.begin=now();
            {Timer t(spans[SERVER]);server.reset(new NFLLWE);server->setsecurityBits(0);setup(*server,w);}
            {Timer t(spans[ENCODE]);encoded.assign(N,Bytes(logical,0));
                for(unsigned i=0;i<N;i++)for(unsigned b=0;b<ell;b++)
                    encoded[i][((b/rho)*w+b%rho)/8]|=((raw[i][b/8]>>(b%8))&1)<<(((b/rho)*w+b%rho)%8);
            }
            {Timer t(spans[IMPORT]);db.reset(new MemoryDB(std::move(encoded)));reply.reset(new NativeReply(p,*db,*server));reply->importDataNFL(0,logical);}
            prep.end=now();
        };
        bool online=job.get<std::string>("preprocess_mode")=="ONLINE";
        if(online)preprocess();
        char ready='R';int readyfd=job.get<int>("ready_fd"),gofd=job.get<int>("go_fd");
        transfer(readyfd,&ready,1,true);uint64_t release=0;transfer(gofd,&release,8,false);
        while(now()<release){timespec delay{0,100000};nanosleep(&delay,nullptr);}
        auto inject=job.get<std::string>("inject","");
        if(inject=="timeout"){sleep(120);return 9;}
        if(inject=="runtime")return 17;
        if(inject=="resource")return 18;
        rusage before{},after{};getrusage(RUSAGE_SELF,&before);
        uint64_t task_begin=now(),key_before=0,key_after=0,query_before=0,query_after=0,qbytes=0,rbytes=0,qcount=0,rcount=0;
        if(inject=="lag"){timespec delay{0,50000000};nanosleep(&delay,nullptr);} // Dry-run critical-path assertion only.
        {Timer t(spans[CONFIG]);client.reset(new NFLLWE);client->setsecurityBits(0);}
        {Timer t(spans[KEY]);key_before=rng_calls;setup(*client,w);key_after=rng_calls;}
        if(!online)preprocess();
        {Timer t(spans[QUERY]);query_before=rng_calls;reply->initQueriesBuffer();
            for(unsigned i=0;i<N;i++){
                char* cipher=client->encrypt(messages[i],1);
                size_t size=client->publicParams.getCiphertextBitsize()/8;
                std::vector<char> wire(cipher,cipher+size);
                char* received=static_cast<char*>(malloc(wire.size()));
                memcpy(received,wire.data(),wire.size());free(cipher);
                qbytes+=wire.size();++qcount;reply->pushQuery(received,wire.size(),0,i);
            }query_after=rng_calls;
        }
        {Timer t(spans[REPLY]);reply->evaluate();}
        {Timer t(spans[EXTRACT]);decoded.assign(targets.size(),Bytes((ell+7)/8,0));
            for(uint64_t block=0;block<L;block++){
                size_t size=client->publicParams.getCiphertextBitsize()/8;
                std::vector<char> wire(reply->repliesArray[block],reply->repliesArray[block]+size);
                rbytes+=wire.size();++rcount;
                unsigned char* plain=reinterpret_cast<unsigned char*>(client->decrypt(wire.data(),1,wire.size(),DEG*w/8));
                for(uint64_t j=0;j<DEG && block*DEG+j<J;j++){
                    uint64_t y=0;for(unsigned b=0;b<w;b++)y|=uint64_t((plain[(j*w+b)/8]>>((j*w+b)%8))&1)<<b;
                    for(size_t k=0;k<targets.size();k++)for(unsigned b=0;b<rho && (block*DEG+j)*rho+b<ell;b++){
                        uint64_t out=(block*DEG+j)*rho+b;decoded[k][out/8]|=((y>>(k*rho+b))&1)<<(out%8);
                    }
                }free(plain);
            }
        }
        uint64_t task_end=now();getrusage(RUSAGE_SELF,&after);
        // Do not let a faster worker validate while its peer is still timed.
        char done='D';transfer(readyfd,&done,1,true);char validate_gate=0;
        transfer(gofd,&validate_gate,1,false);close(readyfd);close(gofd);
        // Everything below is excluded from TaskTotal and all performance phases.
        ptree result,phase,events,actual,expected,affinity;
        bool correct=true;std::string raw_hash,encoded_hash,key_hash;
        {Timer t(spans[VALIDATE]);
            if(inject=="wrong")decoded[0][0]^=1;
            for(size_t k=0;k<targets.size();k++){
                correct&=decoded[k]==raw[targets[k]];ptree a,e;
                a.put("",hex(decoded[k].data(),decoded[k].size()));e.put("",hex(raw[targets[k]].data(),raw[targets[k]].size()));actual.push_back({"",a});expected.push_back({"",e});
            }
            raw_hash=digest(raw);encoded_hash=digest(db->data);
            unsigned char key_digest[32];SHA256(reinterpret_cast<unsigned char*>(client->getsecretKey()[0]),DEG*8,key_digest);
            key_hash=hex(key_digest,32); // Diagnostic uniqueness only, never a security estimate.
            require(client->getnbModuli()==2 && client->getpolyDegree()==DEG,"backend degree");
            require(client->getmoduli()[0]==2305843009213317121ULL && client->getmoduli()[1]==2305843009213120513ULL,"moduli");
            require(client->publicParams.getAbsorptionBitsize()==DEG*w && client->publicParams.getnoiseUB()==200,"width/noise");
            require(db->reads==N && reply->blocks()==L,"import");
            require(key_after-key_before==1 && query_after-query_before==2*N && rng_calls==2+2*N && rng_sequence,"fresh RNG path");
            require(qbytes==N*CT && rbytes==L*CT,"payload ABI");
        }
        for(unsigned i=0;i<COUNT;i++){phase.put(names[i],spans[i].end-spans[i].begin);
            ptree s;s.put("begin",spans[i].begin);s.put("end",spans[i].end);events.add_child(names[i],s);}
        cpu_set_t mask;CPU_ZERO(&mask);sched_getaffinity(0,sizeof(mask),&mask);
        for(int i=0;i<CPU_SETSIZE;i++)if(CPU_ISSET(i,&mask)){ptree v;v.put("",i);affinity.push_back({"",v});}
        timespec resolution;clock_getres(CLOCK_MONOTONIC_RAW,&resolution);
        result.put("pid",getpid());result.put("ppid",getppid());result.put("task_start_ns",task_begin);result.put("task_end_ns",task_end);
        result.put("task_total_ns",task_end-task_begin);result.put("release_ns",release);
        result.put("preprocess_start_ns",prep.begin);result.put("preprocess_end_ns",prep.end);
        result.put("cpu_user_ns",cpu(after.ru_utime)-cpu(before.ru_utime));result.put("cpu_system_ns",cpu(after.ru_stime)-cpu(before.ru_stime));
        getrusage(RUSAGE_SELF,&after);result.put("peak_rss_kib",after.ru_maxrss);
        result.put("query_ciphertexts",qcount);result.put("reply_ciphertexts",rcount);result.put("query_payload_bytes",qbytes);result.put("reply_payload_bytes",rbytes);
        result.put("db_fixture_hash",raw_hash);result.put("encoded_db_hash",encoded_hash);result.put("key_fingerprint",key_hash);
        result.put("key_generation_calls",1);result.put("server_unused_key_generation_calls",1);result.put("query_encrypt_calls",N);
        result.put("rng_calls",rng_calls);result.put("clock_resolution_ns",uint64_t(resolution.tv_sec)*1000000000+resolution.tv_nsec);
        result.put("status",correct?"COMPLETE":"WRONG_OUTPUT");result.put("failure_reason",correct?"":"ordered output mismatch");
        result.put("output_verified",correct);result.put("omp_max_threads",omp_get_max_threads());
        result.put("validation_release_seen",validate_gate=='V');
        result.add_child("phase_ns",phase);result.add_child("phase_events",events);result.add_child("actual_hex",actual);result.add_child("expected_hex",expected);result.add_child("cpu_affinity",affinity);
        write_json(argv[2],result);return correct?0:20;
    }catch(const std::exception& e){std::cerr<<"worker exception: "<<e.what()<<'\n';return 21;}
}
