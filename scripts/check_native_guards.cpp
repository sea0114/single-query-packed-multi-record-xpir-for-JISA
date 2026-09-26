// SPDX-License-Identifier: GPL-3.0-or-later
// Functional-only checks of the unchanged adapter's rejected public domains.
#include "m1_adapter.hpp"
#include <functional>
#include <iostream>
static int rejected=0;
static void reject(const std::function<void()>& f) {
    try { f(); } catch (const std::runtime_error&) { ++rejected; return; }
    throw std::runtime_error("Expected adapter rejection was absent");
}
int main() {
    reject([]{m1::Layout l(256,8,0,4096);});
    reject([]{m1::Layout l(256,16,64,4096);});
    reject([]{m1::Layout l(256,16,48,4096);m1::validate_weights(l,m1::radix_weights(l,3));});
    reject([]{m1::Layout l(256,12,48,4096);m1::validate_weights(l,m1::radix_weights(l,4));});
    reject([]{m1::Layout l(256,8,16,4096);m1::radix_weights(l,3);});
    reject([]{m1::Layout l(256,8,16,4096);m1::validate_weights(l,{1,255});});
    m1::Layout supported(257,8,32,4096);
    m1::validate_weights(supported,m1::radix_weights(supported,4));
    std::cout << "{\"status\":\"PASS\",\"rejections\":" << rejected
              << ",\"supported_profile\":true,\"performance_observations\":0}\n";
}
