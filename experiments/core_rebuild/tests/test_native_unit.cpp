// SPDX-License-Identifier: GPL-3.0-or-later
// Standalone native wrapper tests; no performance observations or cryptographic initialization.
#include "core_native.hpp"
#include <functional>
#include <iostream>
#include <signal.h>
#include <sys/resource.h>
#include <sys/wait.h>

using namespace core_rebuild;
void rejects(const std::function<void()>& function) {
    bool rejected=false;try{function();}catch(const std::exception&){rejected=true;}
    require(rejected,"expected invalid-domain rejection");
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: test_native_unit NEW_MAPPING_PATH");
        uint64_t checks=0;
        for(uint64_t rho:{4,6,8,12,16,24}) {
            for(uint64_t ell:{DEGREE*rho-1,DEGREE*rho,DEGREE*rho+1,2*DEGREE*rho}) {
                Layout layout(ell,rho);const auto raw=fixture(4,layout,0x1122334455667788ULL,"pseudorandom");
                std::vector<std::vector<uint64_t>> all_segments;
                for(const auto& bytes:raw)all_segments.push_back(layout.segments(bytes));
                for(const auto& bytes:raw) {
                    const auto fields=layout.segments(bytes);require(layout.decode(fields)==bytes,"bit-boundary roundtrip");
                    const auto encoded=layout.encode(bytes);
                    for(uint64_t i=0;i<fields.size();++i) {
                        uint64_t actual=0;
                        for(uint64_t bit=0;bit<WIDTH;++bit)actual|=uint64_t((encoded[(i*WIDTH+bit)/8]>>((i*WIDTH+bit)%8))&1)<<bit;
                        require(actual==fields[i],"zero extension/import field mismatch");
                    }
                }
                for(size_t alpha=1;alpha<=4 && alpha*rho<=WIDTH;++alpha) {
                    const auto weights=layout.weights(alpha);sufficient_screen(4096,layout,alpha);
                    for(uint64_t i=0;i<layout.fields();++i) {
                        uint64_t packed=0;for(size_t k=0;k<alpha;++k)packed+=weights[k]*all_segments[k][i];
                        require(packed<layout.t(),"packed plaintext capacity");
                        for(size_t k=0;k<alpha;++k)require((packed/weights[k])%layout.B()==all_segments[k][i],"ordered radix recovery");
                    }
                    ++checks;
                }
            }
        }
        rejects([]{Layout(0,8);});rejects([]{Layout(128,25);});rejects([]{Layout(128,12).weights(3);});
        {Layout layout(17,8);auto fields=layout.segments(Bytes{0xff,0xff,1});fields[layout.J]=1;rejects([&]{layout.decode(fields);});}
        {Layout layout(17,8);auto fields=layout.segments(Bytes{0xff,0xff,1});fields[layout.J-1]|=2;rejects([&]{layout.decode(fields);});}
        {Layout layout(17,8);rejects([&]{layout.segments(Bytes{0xff,0xff,0xff});});}
        // Toy imported arrays have the same native shape, but require no keys or RNG state.
        Layout layout(DEGREE*12+1,12);const uint64_t N=2;
        std::vector<std::vector<uint64_t>> data(N,std::vector<uint64_t>(layout.L*DEGREE*2));
        std::vector<std::vector<poly64>> pointers(N,std::vector<poly64>(layout.L));std::vector<lwe_in_data> rows(N);
        for(uint64_t i=0;i<N;++i) {
            for(uint64_t j=0;j<data[i].size();++j)data[i][j]=i*100000+j;
            for(uint64_t b=0;b<layout.L;++b)pointers[i][b]=data[i].data()+b*DEGREE*2;
            rows[i].p=pointers[i].data();rows[i].nbPolys=layout.L;
        }
        export_mapping(argv[1],rows.data(),N,layout,99);
        {
            ReadOnlyMapping mapping(argv[1],N,layout,99);
            require(mapping.bytes()==DATA_OFFSET+imported_bytes(N,layout),"mapping total byte count");
            for(uint64_t i=0;i<N;++i)for(uint64_t j=0;j<data[i].size();++j)
                require(mapping.data()[i*data[i].size()+j]==data[i][j],"mapping native coefficient order");
            rejects([&]{ReadOnlyMapping wrong(argv[1],N,layout,98);});
            // This fork occurs before any cryptographic initialization, solely to test OS write protection.
            rlimit core_limit{0,0};require(setrlimit(RLIMIT_CORE,&core_limit)==0,"cannot disable protection-probe core dump");
            const pid_t child=fork();require(child>=0,"write-protection probe fork failed");
            if(!child){const_cast<uint64_t*>(mapping.data())[0]=123;_exit(0);}
            int status=0;require(waitpid(child,&status,0)==child,"write-protection probe wait failed");
            require(WIFSIGNALED(status) && (WTERMSIG(status)==SIGSEGV || WTERMSIG(status)==SIGBUS),"borrowed mapping was writable");
            require(mapping.data()[0]==data[0][0],"read-only probe altered shared coefficients");
        }
        std::cout<<"{\"status\":\"PASS_NATIVE_WRAPPER_UNIT\",\"layout_alpha_checks\":"<<checks<<",\"cryptographic_initializations\":0,\"measurements\":0}\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
