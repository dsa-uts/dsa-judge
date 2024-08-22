-- データベースの作成
CREATE DATABASE IF NOT EXISTS task CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- データベースを使用
USE task;

-- Lectureテーブルの作成
CREATE TABLE IF NOT EXISTS Lecture (
    id INT AUTO_INCREMENT PRIMARY KEY, -- 授業エントリのID
    title VARCHAR(255) NOT NULL, -- 授業のタイトル名 e.g., 課題1, 課題2, ...
    start_date TIMESTAMP NOT NULL, -- 課題ページの公開日
    end_date TIMESTAMP NOT NULL -- 課題ページの公開終了日
);

-- Lectureテーブルに初期データを挿入
INSERT INTO Lecture (title, start_date, end_date) VALUES
('課題1', '2023-10-01 00:00:00', '2025-12-31 23:59:59');

-- Problemテーブルの作成
CREATE TABLE IF NOT EXISTS Problem (
    lecture_id INT NOT NULL, -- Lecture.idからの外部キー
    assignment_id INT NOT NULL, -- 何番目の課題か, e.g., 1, 2, ...
    for_evaluation BOOLEAN NOT NULL, -- 課題採点用かどうか, True/False
    title VARCHAR(255) NOT NULL, -- 課題名 e.g., 基本課題1
    description_path VARCHAR(255) NOT NULL, -- 課題の説明文のファイルパス
    timeMS INT NOT NULL, -- ジャッジの制限時間[ms] e.g., 1000
    memoryMB INT NOT NULL, -- ジャッジの制限メモリ[MB] e.g., 1024
    build_script_path VARCHAR(255) NOT NULL, -- ビルドする際に用いるスクリプトファイルのパス
    executable VARCHAR(255) NOT NULL, -- 最終的に得られる実行バイナリ名 e.g., main
    PRIMARY KEY (lecture_id, assignment_id, for_evaluation),
    FOREIGN KEY (lecture_id) REFERENCES Lecture(id)
);

-- Problemテーブルに初期データを挿入
INSERT INTO Problem (lecture_id, assignment_id, for_evaluation, title, description_path, timeMS, memoryMB, build_script_path, executable) VALUES
(1, 1, false, "基本課題", "ex1-1/description.md", 1000, 1024, "ex1-1/build.sh", "gcd_euclid"),
(1, 1, true , "基本課題", "ex1-1/description.md", 1000, 1024, "ex1-1/build.sh", "gcd_euclid"),
(1, 2, false, "発展課題", "ex1-2/description.md", 1000, 1024, "ex1-2/build.sh", "gcd_recursive");

-- ArrangedFilesテーブル(あらかじめこちらで用意したファイルリスト)の作成
CREATE TABLE IF NOT EXISTS ArrangedFiles (
    id INT AUTO_INCREMENT PRIMARY KEY, -- ソースコードのID(auto increment)
    lecture_id INT, -- 何回目の授業で出される課題か, e.g., 1, 2, ...
    assignment_id INT, -- 何番目の課題か, e.g., 1, 2, ...
    for_evaluation BOOLEAN, -- 課題採点用かどうか, True/False
    path VARCHAR(255) NOT NULL, -- ソースコードのパス(Makefileも全部含める)
    FOREIGN KEY (lecture_id, assignment_id, for_evaluation) REFERENCES Problem(lecture_id, assignment_id, for_evaluation)
);

-- ArrangedFilesテーブルに初期データを挿入
-- INSERT INTO ArrangedFiles (lecture_id, assignment_id, for_evaluation, path) VALUES

-- RequiredFilesテーブル(ユーザに提出を求めれているファイルのリスト)の作成
CREATE TABLE IF NOT EXISTS RequiredFiles (
    id INT AUTO_INCREMENT PRIMARY KEY, -- ソースコードのID(auto increment)
    lecture_id INT, -- 何回目の授業で出される課題か, e.g., 1, 2, ...
    assignment_id INT, -- 何番目の課題か, e.g., 1, 2, ...
    for_evaluation BOOLEAN, -- 課題採点用かどうか, True/False
    name VARCHAR(255) NOT NULL, -- 提出が求められるファイルの名前
    FOREIGN KEY (lecture_id, assignment_id, for_evaluation) REFERENCES Problem(lecture_id, assignment_id, for_evaluation)
);

-- RequiredFilesテーブルに初期データを挿入
INSERT INTO RequiredFiles (lecture_id, assignment_id, for_evaluation, name) VALUES
(1, 1, false, "gcd_euclid.c"),
(1, 1, false, "main_euclid.c"),
(1, 1, false, "Makefile"),
(1, 1, true , "gcd_euclid.c"),
(1, 1, true , "main_euclid.c"),
(1, 1, true , "Makefile"),
(1, 2, false, "gcd_recursive.c"),
(1, 2, false, "main_recursive.c"),
(1, 2, false, "Makefile");

-- TestCasesテーブルの作成
CREATE TABLE IF NOT EXISTS TestCases (
    id INT AUTO_INCREMENT PRIMARY KEY, -- テストケースのID(auto increment)
    lecture_id INT NOT NULL, -- 何回目の授業で出される課題か, e.g., 1, 2, ...
    assignment_id INT NOT NULL, -- 何番目の課題か, e.g., 1, 2, ...
    for_evaluation BOOLEAN NOT NULL, -- 課題採点用かどうか, True/False
    type ENUM('preBuilt', 'postBuilt', 'Judge') NOT NULL, -- テストケースが実行されるタイミング
    description TEXT, -- どの部分点に相当するかの説明
    score INT, -- テストケースの配点, フォーマットチェック用だったらゼロ
    script_path VARCHAR(255), -- ./<実行バイナリ> の形式に合わない場合のスクリプトファイルのパス
    argument_path VARCHAR(255), -- スクリプトもしくは実行バイナリに渡す引数が記されたファイルのパス
    stdin_path VARCHAR(255), -- 標準入力のパス, path/to/stdin.txt
    stdout_path VARCHAR(255) NOT NULL, -- 想定される標準出力のパス, path/to/stdout.txt
    stderr_path VARCHAR(255) NOT NULL, -- 想定される標準エラー出力のパス, path/to/stderr.txt
    exit_code INT NOT NULL DEFAULT 0, -- 想定される戻り値
    FOREIGN KEY (lecture_id, assignment_id, for_evaluation) REFERENCES Problem(lecture_id, assignment_id, for_evaluation)
);

-- TestCasesテーブルに初期データを挿入
INSERT INTO TestCases 
(lecture_id, assignment_id, for_evaluation, type        , description                                        , score, script_path            , argument_path                    , stdin_path, stdout_path                     , stderr_path                     , exit_code) VALUES
(1         , 1            , false         , 'preBuilt'  , "指定したファイルを提出しているか"                       , 0    , "filecheck.sh"         , "ex1-1/filecheck.arg"            , NULL      , "ex1-1/filecheck.stdout"        , "ex1-1/filecheck.stderr"        , 0),
(1         , 1            , false         , 'postBuilt' , "gcd_euclid関数がgcd_euclid.cに定義されているかチェック" , 0    , "ex1-1/compilecheck.sh", NULL                             , NULL      , "ex1-1/compilecheck.stdout"     , "ex1-1/compilecheck.stderr"     , 0),
(1         , 1            , false         , 'Judge'     , "小さい数同士のGCDを求められているか"                    , 10   , NULL                   , "ex1-1/testcases/easy1.arg"      , NULL      , "ex1-1/testcases/easy1.out"     , "ex1-1/testcases/easy1.err"     , 0),
(1         , 1            , false         , 'Judge'     , "小さい数同士のGCDを求められているか"                    , 10   , NULL                   , "ex1-1/testcases/easy2.arg"      , NULL      , "ex1-1/testcases/easy2.out"     , "ex1-1/testcases/easy2.err"     , 0),
(1         , 1            , false         , 'Judge'     , "小さい数同士のGCDを求められているか"                    , 10   , NULL                   , "ex1-1/testcases/easy3.arg"      , NULL      , "ex1-1/testcases/easy3.out"     , "ex1-1/testcases/easy3.err"     , 0),
(1         , 1            , false         , 'Judge'     , "小さい数同士のGCDを求められているか"                    , 10   , NULL                   , "ex1-1/testcases/easy4.arg"      , NULL      , "ex1-1/testcases/easy4.out"     , "ex1-1/testcases/easy4.err"     , 0),
(1         , 1            , false         , 'Judge'     , "引数が多いケースをチェックできているか"                  , 10   , NULL                   , "ex1-1/testcases/exception1.arg" , NULL      , "ex1-1/testcases/exception1.out", "ex1-1/testcases/exception1.err", 1),
(1         , 1            , false         , 'Judge'     , "ゼロ以下の整数を与えられたケース"                       , 10   , NULL                   , "ex1-1/testcases/exception1.arg" , NULL      , "ex1-1/testcases/exception1.out", "ex1-1/testcases/exception1.err", 1);


-- AdminUserテーブルの作成
CREATE TABLE IF NOT EXISTS AdminUser (
    id VARCHAR(255) PRIMARY KEY, -- ユーザID e.g., zakki
    name VARCHAR(255) NOT NULL -- ユーザ名 e.g., 山崎
);

-- AdminUserテーブルに初期データを挿入
INSERT INTO AdminUser (id, name) VALUES
('takuyamizokami', "Takuya Mizokami");

-- Studentテーブルの作成
CREATE TABLE IF NOT EXISTS Student (
    id VARCHAR(255) PRIMARY KEY, -- 学籍番号 e.g., s2200342
    name VARCHAR(255) NOT NULL -- ユーザ名 e.g., 岡本
);

-- Studentテーブルに初期データを挿入
INSERT INTO Student (id, name) VALUES
("sxxxxxxx", "溝上 拓也");

-- BatchSubmissionテーブルの作成
CREATE TABLE IF NOT EXISTS BatchSubmission (
    id INT AUTO_INCREMENT PRIMARY KEY, -- バッチ採点のID(auto increment)
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- バッチ採点のリクエスト時刻
    user_id VARCHAR(255), -- リクエストした管理者のID
    FOREIGN KEY (user_id) REFERENCES AdminUser(id)
);

-- Submissionテーブルの作成
CREATE TABLE IF NOT EXISTS Submission (
    id INT AUTO_INCREMENT PRIMARY KEY, -- 提出されたジャッジリクエストのID(auto increment)
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- リクエストされた時刻
    batch_id INT, -- ジャッジリクエストが属しているバッチリクエストのID, 学生のフォーマットチェック提出ならNULL
    student_id VARCHAR(255) NOT NULL, -- 採点対象の学生の学籍番号
    lecture_id INT NOT NULL, -- 何回目の授業で出される課題か, e.g., 1, 2, ...
    assignment_id INT NOT NULL, -- 何番目の課題か, e.g., 1, 2, ...
    for_evaluation BOOLEAN NOT NULL, -- 課題採点用かどうか, True/False
    progress ENUM('pending', 'queued', 'running', 'done') DEFAULT 'pending', -- リクエストの処理状況, pending/queued/running/done
    prebuilt_result ENUM('Unprocessed', 'AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE') DEFAULT 'Unprocessed', -- prebuiltチェックの結果
    postbuilt_result ENUM('Unprocessed', 'AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE') DEFAULT 'Unprocessed', -- postbuiltチェックの結果
    judge_result ENUM('Unprocessed', 'AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE') DEFAULT 'Unprocessed', -- ジャッジ結果
    message VARCHAR(255) DEFAULT '',
    FOREIGN KEY (batch_id) REFERENCES BatchSubmission(id),
    FOREIGN KEY (student_id) REFERENCES Student(id),
    FOREIGN KEY (lecture_id, assignment_id, for_evaluation) REFERENCES Problem(lecture_id, assignment_id, for_evaluation)
);

-- UploadedFilesテーブルの作成
CREATE TABLE IF NOT EXISTS UploadedFiles (
    id INT AUTO_INCREMENT PRIMARY KEY, -- アップロードされたファイルのID(auto increment)
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- アップロードされた時刻
    submission_id INT, -- そのファイルが必要なジャッジリクエストのID
    path VARCHAR(255) NOT NULL, -- アップロードされたファイルのパス
    FOREIGN KEY (submission_id) REFERENCES Submission(id)
);

-- JudgeResultテーブルの作成
CREATE TABLE IF NOT EXISTS JudgeResult (
    id INT AUTO_INCREMENT PRIMARY KEY, -- ジャッジ結果のID(auto increment)
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- ジャッジ結果が出た時刻
    submission_id INT, -- ジャッジ結果に紐づいているジャッジリクエストのID
    testcase_id INT, -- ジャッジ結果に紐づいているテストケースのID
    timeMS INT NOT NULL, -- 実行時間[ms]
    memoryKB INT NOT NULL, -- 消費メモリ[KB]
    exit_code INT NOT NULL, -- 戻り値
    stdout TEXT NOT NULL, -- 標準出力
    stderr TEXT NOT NULL, -- 標準エラー出力
    result ENUM('AC', 'WA', 'TLE', 'MLE', 'CE', 'RE', 'OLE', 'IE') NOT NULL, -- 実行結果のステータス、 AC/WA/TLE/MLE/CE/RE/OLE/IE, 参考: https://atcoder.jp/contests/abc367/glossary
    FOREIGN KEY (submission_id) REFERENCES Submission(id),
    FOREIGN KEY (testcase_id) REFERENCES TestCases(id)
);
