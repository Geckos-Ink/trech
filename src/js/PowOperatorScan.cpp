#include "trech/js/PowOperatorScan.hpp"

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <string>

namespace trech {
namespace {

bool isWordChar(char c) {
  return std::isalnum(static_cast<unsigned char>(c)) != 0 || c == '_' || c == '$';
}

bool regexKeyword(std::string_view word) {
  static constexpr std::string_view kWords[] = {"return", "typeof", "instanceof", "in", "of",
                                                "new", "delete", "void", "throw", "case", "do",
                                                "else", "yield", "await"};
  return std::find(std::begin(kWords), std::end(kWords), word) != std::end(kWords);
}

class Scanner {
public:
  explicit Scanner(std::string_view text) : text_(text) {
    lineStarts_.push_back(0);
    for (std::size_t i = 0; i < text_.size(); ++i)
      if (text_[i] == '\n') lineStarts_.push_back(i + 1);
  }

  std::vector<std::pair<int, int>> run() {
    scan(0, '\0');
    return std::move(hits_);
  }

private:
  bool startsWith(std::size_t i, std::string_view token) const {
    return text_.substr(i, token.size()) == token;
  }

  std::pair<int, int> position(std::size_t index) const {
    const auto line = std::upper_bound(lineStarts_.begin(), lineStarts_.end(), index) - 1;
    return {static_cast<int>(line - lineStarts_.begin()) + 1,
            static_cast<int>(index - *line) + 1};
  }

  std::size_t skipString(std::size_t i, char quote) const {
    ++i;
    while (i < text_.size() && text_[i] != quote) i += text_[i] == '\\' ? 2 : 1;
    return i + 1;
  }

  std::size_t skipRegex(std::size_t i) const {
    ++i;
    bool inClass = false;
    while (i < text_.size() && text_[i] != '\n') {
      const char c = text_[i];
      if (c == '\\') {
        i += 2;
        continue;
      }
      if (c == '[') {
        inClass = true;
      } else if (c == ']') {
        inClass = false;
      } else if (c == '/' && !inClass) {
        ++i;
        while (i < text_.size() && (std::isalnum(static_cast<unsigned char>(text_[i])) || text_[i] == '_')) ++i;
        return i;
      }
      ++i;
    }
    return i;
  }

  // Scan code from i until an unmatched `closing` brace (or the end); return its index.
  std::size_t scan(std::size_t i, char closing) {
    int depth = 0;
    std::string previous;  // last significant character, or a regex keyword, or "a"
    const std::size_t n = text_.size();
    while (i < n) {
      const char c = text_[i];
      if (std::isspace(static_cast<unsigned char>(c))) {
        ++i;
        continue;
      }
      if (startsWith(i, "//")) {
        const auto end = text_.find('\n', i);
        i = end == std::string_view::npos ? n : end;
        continue;
      }
      if (startsWith(i, "/*")) {
        const auto end = text_.find("*/", i + 2);
        i = end == std::string_view::npos ? n : end + 2;
        continue;
      }
      if (c == '"' || c == '\'') {
        i = skipString(i, c);
        previous = "a";
        continue;
      }
      if (c == '`') {
        ++i;
        while (i < n && text_[i] != '`') {
          if (text_[i] == '\\') {
            i += 2;
          } else if (startsWith(i, "${")) {
            i = scan(i + 2, '}') + 1;
          } else {
            ++i;
          }
        }
        ++i;
        previous = "a";
        continue;
      }
      if (c == '/') {
        static constexpr std::string_view kRegexAfter = "(,=:[!&|?{};+-*%<>~^";
        const bool afterPunctuator = previous.size() == 1 &&
                                     kRegexAfter.find(previous[0]) != std::string_view::npos;
        if (previous.empty() || afterPunctuator || regexKeyword(previous)) {
          i = skipRegex(i);
          previous = "a";
          continue;
        }
      }
      if (startsWith(i, "**")) {
        hits_.push_back(position(i));
        i += startsWith(i, "**=") ? 3 : 2;
        previous = "*";
        continue;
      }
      if (isWordChar(c)) {
        const std::size_t start = i;
        while (i < n && isWordChar(text_[i])) ++i;
        const auto word = text_.substr(start, i - start);
        previous = regexKeyword(word) ? std::string(word) : std::string("a");
        continue;
      }
      if (c == '{') {
        ++depth;
      } else if (c == '}') {
        if (depth == 0 && closing == '}') return i;
        --depth;
      }
      previous = (c == ')' || c == ']') ? std::string("a") : std::string(1, c);
      ++i;
    }
    return i;
  }

  std::string_view text_;
  std::vector<std::size_t> lineStarts_;
  std::vector<std::pair<int, int>> hits_;
};

}  // namespace

std::vector<std::pair<int, int>> findJsPowOperators(std::string_view source) {
  return Scanner(source).run();
}

}  // namespace trech
