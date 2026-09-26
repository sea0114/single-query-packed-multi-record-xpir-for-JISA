"""Auditable additive derivation from frozen B1 measurement code and B2-A build."""
from b2b_common import *
def derive_worker():
    s=(ROOT/'tools/benchmark/worker.cpp').read_text()
    def replace(a,b):
        nonlocal s
        assert s.count(a)==1,(a,s.count(a));s=s.replace(a,b)
    replace('// B0 measurement adapter. Validation and formatting run after task_end.','// B2-B generalized measurement adapter. B1 endpoints, B2-A exact validation.\n#include "../../native_xpir/m1_adapter.hpp"')
    replace('SEED=0x42305f4441544131ULL',f'SEED={hex(DATA_SEED)}ULL')
    replace('struct Span{','bool timing_enabled=true;\nuint64_t stamp(){return timing_enabled?now():0;}\nstruct Span{')
    replace('s.begin=now();}~Timer(){s.end=now();','s.begin=stamp();}~Timer(){s.end=stamp();')
    replace('B0 frozen fixture','B2-B frozen fixture')
    replace('unsigned N=job.get<unsigned>("N"),ell=job.get<unsigned>("ell_bits"),rho=job.get<unsigned>("rho_0"),w=2*rho;\n        require(N>=2 && ell>0 && ell<=2048 && (rho==8||rho==12||rho==16),"preflight domain");', '''unsigned N=job.get<unsigned>("N"),ell=job.get<unsigned>("ell_bits"),rho=job.get<unsigned>("rho_0"),a=job.get<unsigned>("alpha"),w=job.get<unsigned>("w");
        const bool functional=job.get<std::string>("timing_label")=="FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE";
        timing_enabled=!functional;
        require(functional || job.get<std::string>("timing_label")=="FORMAL","timing label");
        require((a==2||a==3||a==4) && rho==8 && w==a*rho,"B2-B profile");
        require(functional?(N==8 && ell==256):((N==1024||N==4096)&&(ell==512||ell==2048)),"B2-B workload");
        m1::Layout layout(ell,rho,w,DEG);
        auto all_weights=m1::radix_weights(layout,a);m1::validate_weights(layout,all_weights);
        const std::string method=job.get<std::string>("method");
        require(method=="packed"||method=="repeated","method");''')
    replace('require(targets.size()==1||targets.size()==2,"alpha");for(auto i:targets)require(i<N,"target range");\n        require(targets.size()==1||targets[0]!=targets[1],"distinct targets");', '''require(targets.size()==(method=="packed"?a:1),"request multiplicity");
        for(size_t k=0;k<targets.size();++k){
            unsigned r=method=="packed"?k:job.get<unsigned>("worker_index");
            require(r<a && targets[k]==((2*r+1)*N)/(2*a),"canonical ordered target");
        }
        auto K=m1::radix_weights(layout,targets.size());m1::validate_weights(layout,K);''')
    replace('messages[targets[k]]=uint64_t(1)<<(rho*k);','messages[targets[k]]=K[k];')
    replace('Span spans[COUNT],prep;DB encoded,decoded;','Span spans[COUNT],prep;DB encoded,decoded;std::vector<uint64_t> packed;std::vector<std::vector<uint64_t>> unpacked(targets.size());')
    replace('prep.begin=now();','prep.begin=stamp();');replace('prep.end=now();','prep.end=stamp();')
    start=s.index('        auto inject=job.get<std::string>');end=s.index('        rusage before',start)
    s=s[:start]+s[end:]
    replace('uint64_t task_begin=now(),','uint64_t task_begin=stamp(),')
    replace('        if(inject=="lag"){timespec delay{0,50000000};nanosleep(&delay,nullptr);} // Dry-run critical-path assertion only.\n','')
    replace('char* cipher=client->encrypt(messages[i],1);','char* cipher=m1::encrypt_integer(*client,messages[i]);')
    start=s.index('                for(uint64_t j=0;j<DEG &&');end=s.index('                }free(plain);',start)+len('                }free(plain);')
    s=s[:start]+'''                auto fields=m1::read_fields(plain,DEG,w);free(plain);
                packed.insert(packed.end(),fields.begin(),fields.end());
                for(uint64_t y:fields){
                    // Extract every slot, including polynomial padding. Validation follows the completion barrier.
                    for(size_t k=0;k<targets.size();++k)unpacked[k].push_back((y/K[k])%layout.B());
                }'''+s[end:]
    replace('''            }
        }
        uint64_t task_end=now();''','''            }
            for(size_t k=0;k<targets.size();++k){
                for(uint64_t b=0;b<ell;++b)decoded[k][b/8]|=((unpacked[k][b/rho]>>(b%rho))&1)<<(b%8);
            }
        }
        uint64_t task_end=stamp();''')
    replace('            if(inject=="wrong")decoded[0][0]^=1;','''            std::vector<std::vector<uint64_t>> expected_fields;
            for(auto target:targets)expected_fields.push_back(m1::segments(raw[target],layout));
            for(uint64_t j=0;j<L*DEG;++j){
                uint64_t expected_packed=0;
                for(size_t k=0;k<targets.size();++k){expected_packed+=K[k]*expected_fields[k][j];correct&=unpacked[k][j]==expected_fields[k][j];}
                correct&=packed[j]<layout.t() && packed[j]==expected_packed;
            }
            // Exact B2-A Unpack/Decode checks are outside TaskTotal, after every peer has ended.
            for(size_t k=0;k<targets.size();++k){
                try{correct&=m1::decode(unpacked[k],layout)==decoded[k];}catch(const std::exception&){correct=false;}
            }''')
    replace('        write_json(argv[2],result);return correct?0:20;','''        result.put("timing_label",functional?"FUNCTIONAL_ONLY_NOT_FOR_PERFORMANCE":"FORMAL");
        result.put("alpha",a);result.put("request_alpha",targets.size());result.put("rho_0",rho);result.put("w",w);
        result.put("N",N);result.put("ell_bits",ell);result.put("J",J);result.put("L",L);
        result.put("coefficient_checks",L*DEG);result.put("segment_checks",L*DEG*targets.size());result.put("record_checks",targets.size());
        result.put("all_coefficients_exact",correct);result.put("all_segments_exact",correct);result.put("padding_exact",correct);
        result.put("direct_weight_encryption",true);result.put("native_reply_calls",1);result.put("native_decrypt_calls",L);
        if(functional){
            for(const char* key:{"task_start_ns","task_end_ns","task_total_ns","release_ns","preprocess_start_ns","preprocess_end_ns","cpu_user_ns","cpu_system_ns","peak_rss_kib","phase_ns","phase_events","clock_resolution_ns"})result.erase(key);
            ptree fields;for(auto y:packed){ptree item;item.put("",y);fields.push_back({"",item});}result.add_child("packed_coefficients",fields);
            result.put("timing_collected",false);
        }
        write_json(argv[2],result);return correct?0:20;''')
    write(HERE/'b2b_worker.cpp',s)
def derive_build():
    s=(ROOT/'tools/b2/b2_build.py').read_text().replace('from b2_common import *','from b2b_common import *').replace("HERE/'build_v4'","HERE/'build'").replace("LOG/'build_v4.log'","LOG/'build.log'").replace('b2_worker','b2b_worker').replace("'purpose':LABEL","'purpose':'B2-B performance binary; no formal observations during freeze'").replace("str(Q)","CRYPTO['q']")
    start=s.index("       'pre_build_diagnostic':");end=s.index("       'n':4096",start)
    s=s[:start]+"       'derivation':'B1 phase/endpoints and native pipeline; B2-A generalized exact validation; no arithmetic optimization.',\n"+s[end:]
    start=s.index('    cpu=Path(');end=s.index('    print(json.dumps',start)
    s=s[:start]+s[end:]
    write(HERE/'b2b_build.py',s)
if __name__=='__main__':derive_worker();derive_build()
