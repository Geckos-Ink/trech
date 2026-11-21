// findJsPowOperators: the C++ twin of scripts/check_js_pow_operator.py that the V8 backend
// uses to refuse `**` before evaluating a script.
#include "trech/js/PowOperatorScan.hpp"

#include <iostream>
#include <string>
#include <utility>
#include <vector>

namespace {

int failures = 0;

void expect(const std::string& label, const std::string& source,
            const std::vector<std::pair<int, int>>& expected) {
  const auto hits = trech::findJsPowOperators(source);
  if (hits != expected) {
    ++failures;
    std::cerr << "FAIL " << label << ": got";
    for (const auto& [line, column] : hits) std::cerr << " " << line << ":" << column;
    std::cerr << " expected";
    for (const auto& [line, column] : expected) std::cerr << " " << line << ":" << column;
    std::cerr << "\n";
  }
}

}  // namespace

int main() {
  expect("plain operator", "var x = a ** 2;", {{1, 11}});
  expect("assignment", "x **= 3;\ny = 1;", {{1, 3}});
  expect("second line", "var a = 1;\nvar b = a**a;", {{2, 10}});
  expect("Math.pow is fine", "var x = Math.pow(a, 2);", {});
  expect("multiplication", "var x = a * b * c;", {});
  expect("line comment", "// a ** b\nvar x = 1;", {});
  expect("block comment", "/* a ** b */ var x = 1; /** doc */", {});
  expect("double-quoted string", "var s = \"a ** b\";", {});
  expect("single-quoted string with escape", "var s = 'it\\'s ** here';", {});
  expect("template text", "var s = `a ** b`;", {});
  expect("template expression", "var s = `${a ** b}`;", {{1, 14}});
  expect("nested template", "var s = `${`${x**2}`}`;", {{1, 16}});
  expect("regex literal", "var r = /a**/g; var y = 2;", {});
  expect("regex after return", "function f() { return /x**/.test(s); }", {});
  expect("division is not a regex", "var q = a / b ** c;", {{1, 15}});
  expect("regex character class", "var r = /[/]**/; var z = 1;", {});
  expect("two operators", "a ** b; c ** d;", {{1, 3}, {1, 11}});
  expect("operator after closing paren", "(a + b)**2", {{1, 8}});
  if (failures) {
    std::cerr << failures << " pow-operator scan case(s) failed\n";
    return 1;
  }
  std::cout << "pow-operator scan: all cases pass\n";
  return 0;
}
