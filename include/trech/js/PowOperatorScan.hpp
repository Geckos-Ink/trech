#pragma once

#include <string_view>
#include <utility>
#include <vector>

namespace trech {

// (line, column), both 1-based, of every JavaScript exponent operator (`**`, `**=`) in
// `source`. A small tokenizer skips comments, string literals, template text (but scans
// `${...}` expressions) and regular-expression literals, so only real operators count.
// This is the C++ twin of scripts/check_js_pow_operator.py. The V8 backend refuses a script
// with any hit: V8 evaluates `**` with its own pow, not trech_dmath, so it would break
// QuickJS/V8 byte replay (docs/engine/v8.md). Math.pow is identical in both engines.
std::vector<std::pair<int, int>> findJsPowOperators(std::string_view source);

}  // namespace trech
