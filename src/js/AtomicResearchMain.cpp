// Standalone research launcher. All atomic mathematics belongs to the JS core;
// this process supplies only a shell-free C++ -> installed Node/V8 boundary.
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <process.h>
#else
#include <unistd.h>
#endif

#ifndef TRECH_ATOMIC_NODE
#error "TRECH_ATOMIC_NODE must identify the configured Node/V8 executable"
#endif
#ifndef TRECH_ATOMIC_RUNNER
#error "TRECH_ATOMIC_RUNNER must identify the research JavaScript entry point"
#endif

#ifdef _WIN32
namespace {
// The Windows CRT joins _spawnv arguments into a command line. Quote each
// argument using its backslash/quote rules so Node receives the original argv.
std::string quoteWindowsArgument(const std::string& argument) {
  std::string quoted = "\"";
  std::size_t backslashes = 0;
  for (const char character : argument) {
    if (character == '\\') {
      ++backslashes;
      continue;
    }
    quoted.append(character == '"' ? 2 * backslashes + 1 : backslashes, '\\');
    quoted.push_back(character);
    backslashes = 0;
  }
  quoted.append(2 * backslashes, '\\');
  quoted.push_back('"');
  return quoted;
}
} // namespace
#endif

int main(int argc, char** argv) {
  std::vector<std::string> arguments;
  arguments.reserve(static_cast<std::size_t>(argc) + 1);
  arguments.emplace_back(TRECH_ATOMIC_NODE);
  arguments.emplace_back(TRECH_ATOMIC_RUNNER);
  for (int i = 1; i < argc; ++i) arguments.emplace_back(argv[i]);

#ifdef _WIN32
  for (auto& argument : arguments) argument = quoteWindowsArgument(argument);
  std::vector<const char*> nativeArguments;
  nativeArguments.reserve(arguments.size() + 1);
  for (const auto& argument : arguments) nativeArguments.push_back(argument.c_str());
  nativeArguments.push_back(nullptr);
  const auto status = _spawnv(_P_WAIT, TRECH_ATOMIC_NODE, nativeArguments.data());
  if (status != -1) return static_cast<int>(status);
#else
  std::vector<char*> nativeArguments;
  nativeArguments.reserve(arguments.size() + 1);
  for (auto& argument : arguments) nativeArguments.push_back(argument.data());
  nativeArguments.push_back(nullptr);
  // Replacing the process preserves stdout/stderr, signals, and the JS exit
  // status without involving a shell or interpreting user-supplied arguments.
  execv(TRECH_ATOMIC_NODE, nativeArguments.data());
#endif

  const int error = errno;
  std::cerr << "trech-atomic: cannot start configured Node/V8 runtime '"
            << TRECH_ATOMIC_NODE << "': " << std::strerror(error) << '\n';
  return 127;
}
