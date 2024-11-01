#include <nlohmann/json.hpp>
#include <iostream>
#include <chrono>
#include <thread>
#include <fstream>
#include <atomic>
#include <sys/wait.h>
#include <sys/types.h>
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/resource.h>
#include <sstream>
#include <vector>
#include <string>

using json = nlohmann::json;

json readFromStdin() {
  std::string line;
  std::string jsonString;

  while (std::getline(std::cin, line)) {
    jsonString += line;
  }

  try {
    return json::parse(jsonString);
  } catch (const json::parse_error& e) {
    std::printf("Error parsing input JSON: %s\n", e.what());
    exit(1);
  }
}

json readFromFile(const std::string& filename) {
  std::ifstream file(filename);
  if (!file.is_open()) {
    std::perror("Failed to open file");
    exit(1);
  }
  std::string jsonString((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
  return json::parse(jsonString);
}

std::vector<pid_t> get_child_pids(pid_t parent_pid) {
  std::vector<pid_t> children;
  std::string cmd = std::string("pgrep -P ") + std::to_string(parent_pid);

  // コマンドを実行
  FILE* stream = popen(cmd.c_str(), "r");
  if (!stream) {
    throw std::runtime_error("popen failed");
  }

  char buffer[128];
  while (fgets(buffer, sizeof(buffer), stream) != nullptr) {
    pid_t pid = std::stoi(std::string(buffer));
    children.push_back(pid);
  }

  pclose(stream);
  return children;
}

void kill_recursive(pid_t pid) {
  try {
    // まず子プロセスを終了
    std::vector<pid_t> children = get_child_pids(pid);
    for (pid_t child : children) {
      kill_recursive(child);
    }

    // 対象プロセスを終了
    if (kill(pid, SIGKILL) < 0) {
      std::cerr << "Failed to kill process " << pid << std::endl;
    }
  } catch (const std::exception& e) {
    std::cerr << "Error in kill_recursive: " << e.what() << std::endl;
  }
}

int main(int argc, char** argv) {
  json jsonData;
  if (argc == 2) {
    jsonData = readFromFile(argv[1]);
  } else {
    jsonData = readFromStdin();
  }

  /**
   * JSONデータは以下のような形式になっている
   * {
   *   "command": "cmd [args...]",
   *   "stdin": "stdin data",
   *   "timeoutMS": 3000,
   *   "memoryLimitMB": 1024,
   *   "uid": 1000,
   *   "gid": 1000
   * }
   */
  std::string command;
  std::string stdin;
  int timeoutMS = 0;
  int memoryLimitMB = 0;
  int uid = 0;
  int gid = 0;
  try {
    command = jsonData.at("command");
    stdin = jsonData.at("stdin");
    timeoutMS = jsonData.at("timeoutMS");
    memoryLimitMB = jsonData.at("memoryLimitMB");
    uid = jsonData.at("uid");
    gid = jsonData.at("gid");
  } catch (const json::out_of_range& e) {
    std::printf("Key not found: %s\n", e.what());
    exit(1);
  }

  std::vector<std::string> args;
  // commandを空白で分割
  std::string token;
  std::istringstream token_stream(command);
  while (token_stream >> token) {
    args.push_back(token);
  }

  int exit_code = -1;
  std::string stdout_str;
  std::string stderr_str;
  int timeMS = 0;
  int memoryKB = 0;

  int stdout_pipe[2];
  int stderr_pipe[2];

  if (pipe(stdout_pipe) == -1 || pipe(stderr_pipe) == -1) {
    std::perror("pipe failed");
    exit(1);
  }

  pid_t pid = fork();
  if (pid == -1) {
    // フォーク失敗
    std::perror("fork failed");
    exit(1);
  } else if (pid == 0) {
    // 子プロセス
    // 標準出力と標準エラーをパイプにリダイレクト
    close(STDOUT_FILENO);
    close(STDERR_FILENO);
    dup2(stdout_pipe[1], STDOUT_FILENO);
    dup2(stderr_pipe[1], STDERR_FILENO);
    close(stdout_pipe[0]);
    close(stderr_pipe[0]);
    close(stdout_pipe[1]);
    close(stderr_pipe[1]);

    // プロセス権限の変更
    if (setgid(gid) != 0) {
      std::perror("setgid failed");
      exit(1);
    }
    if (setuid(uid) != 0) {
      std::perror("setuid failed");
      exit(1);
    }

    // 標準入力を設定 
    int stdin_pipe[2];
    if (pipe(stdin_pipe) == -1) {
      std::perror("stdin pipe failed");
      exit(1);
    }
    pid_t stdin_pid = fork();
    if (stdin_pid == -1) {
      std::perror("stdin fork failed");
      exit(1);
    } else if (stdin_pid == 0) {
      // stdinデータを書き込む
      close(stdin_pipe[0]);
      int remaining = stdin.size();
      const char* ptr = stdin.c_str();
      while (remaining > 0) {
        int written = write(stdin_pipe[1], ptr, remaining);
        if (written <= 0) {
          std::perror("write to stdin pipe failed");
          exit(1);
        }
        remaining -= written;
        ptr += written;
      }
      close(stdin_pipe[1]);
      // printf("stdin child finished\n");
      exit(0);
    } else {
      // 子プロセスの標準入力を設定
      close(stdin_pipe[1]);
      close(STDIN_FILENO);
      dup2(stdin_pipe[0], STDIN_FILENO);
      close(stdin_pipe[0]);

      char** argv = new char*[args.size() + 1];
      for (size_t i = 0; i < args.size(); i++) {
        argv[i] = const_cast<char*>(args[i].c_str());
      }
      argv[args.size()] = NULL;

      // コマンドを実行
      execvp(argv[0], argv);
      std::perror("execvp failed");
      exit(1);
    }
  } else {
    // 親プロセス
    close(stdout_pipe[1]);
    close(stderr_pipe[1]);

    auto start_time = std::chrono::steady_clock::now();
    std::atomic<bool> finished(false);
    int64_t max_memory = 0;

    // タイムアウト用のタイマースレッド
    std::thread timeout_thread([&]() {
      while (!finished.load()) {
        auto now = std::chrono::steady_clock::now();
        // printf("%ldms elapsed, finished: %d\n", std::chrono::duration_cast<std::chrono::milliseconds>(now - start_time).count(), finished.load());
        if (std::chrono::duration_cast<std::chrono::milliseconds>(now - start_time).count() >= timeoutMS) {
          // タイムアウト
          // printf("timeout, kill %d\n", pid);
          // shで実行している場合、子プロセスが残っているため、再帰的に終了する必要がある。
          // そうしないと、子プロセスが実行され続けてしまうし、stdoutやstderrがパイプにEOFが送られない。
          kill_recursive(pid);
          // printf("waitpid: %d\n", waitpid(pid, NULL, 0));
          break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
    });

    // リソース監視スレッド
    std::thread monitor_thread([&]() {
      std::ifstream mem_file("/sys/fs/cgroup/memory.current");
      while (!finished.load()) {
        // メモリ使用量を取得
        int64_t current_memory;
        if (mem_file.is_open()) {
          mem_file >> current_memory;
          mem_file.seekg(0);
        }

        if (current_memory > max_memory) {
          max_memory = current_memory;
        }

        if (current_memory > static_cast<int64_t>(memoryLimitMB) * 1024 * 1024) {
          // メモリ制限超過
          kill_recursive(pid);
          break;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
      mem_file.close();
    });

    // 子プロセスの終了を待つ
    int status;
    waitpid(pid, &status, 0);
    finished.store(true);
    monitor_thread.join();
    // printf("monitor thread finished\n");
    // 実行時間を計算
    auto end_time = std::chrono::steady_clock::now();
    timeMS = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time).count();

    timeout_thread.join();
    // printf("timeout thread finished\n");

    // 最大メモリ使用量 (KB)
    memoryKB = static_cast<int>(max_memory) / 1024;


    // 標準衆力と標準エラー出力を取得)
    char buffer[4096];
    ssize_t count;
    std::ostringstream stdout_stream;
    while ((count = read(stdout_pipe[0], buffer, sizeof(buffer))) > 0) {
      stdout_stream.write(buffer, count);
    }
    stdout_str = stdout_stream.str();
    // printf("stdout: %s\n", stdout_str.c_str());

    std::ostringstream stderr_stream;
    while ((count = read(stderr_pipe[0], buffer, sizeof(buffer))) > 0) {
      stderr_stream.write(buffer, count);
    }
    stderr_str = stderr_stream.str();
    // printf("stderr: %s\n", stderr_str.c_str());

    close(stdout_pipe[0]);
    close(stderr_pipe[0]);

    if (WIFEXITED(status)) {
      exit_code = WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
      exit_code = 128 + WTERMSIG(status);
    } else {
      exit_code = -1;
    }

    // 結果をJSONで出力
    json result;
    result["exit_code"] = exit_code;
    result["stdout"] = stdout_str;
    result["stderr"] = stderr_str;
    result["timeMS"] = timeMS;
    result["memoryKB"] = memoryKB;
    result["TLE"] = timeoutMS > 0 && timeMS >= timeoutMS;
    result["MLE"] = memoryLimitMB > 0 && memoryKB / 1024 >= memoryLimitMB;
    std::cout << result.dump(4) << std::endl;
  }
}
