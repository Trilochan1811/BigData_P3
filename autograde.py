# ============= legacy code: tester.py =============

import time
from pathlib import Path
import subprocess
from collections import OrderedDict
import json
import argparse
import os
import traceback
import shutil
import multiprocessing

multiprocessing.set_start_method("fork")

VERBOSE = True

TMP_DIR = "/tmp/_cs544_tester_directory"
TEST_DIR = None

# full list of tests
INIT = None
TESTS = OrderedDict()
PASSED_TESTS = set()
CLEANUP = None
DEBUG = None
GO_FOR_DEBUG = None

# dataclass for storing test object info


class TestPoint:
    def __init__(self, point, desc=None):
        self.point = point
        self.desc = desc


class _unit_test:
    def __init__(self, func, points, timeout, desc, required_files, dependencies):
        self.func = func
        self.points = points
        self.timeout = timeout
        self.desc = desc
        self.required_files = required_files
        self.dependencies = dependencies

    def run(self, ret):
        points = 0

        # check if required tests passed
        for test_name in self.dependencies:
            if test_name not in PASSED_TESTS:
                result = f"Dependency {test_name} did not pass"
                ret.send((points, result))
                return

        # check if required files exist
        for file in self.required_files:
            if not os.path.exists(file):
                result = f"{file} not found"
                ret.send((points, result))
                return

        try:
            result = self.func()
            if not result:
                points = self.points
                result = f"PASS ({self.points}/{self.points})"
            if isinstance(result, TestPoint):
                points = result.point
                if points == self.points:
                    verdict = "PASS"
                elif points == 0:
                    verdict = "FAIL"
                else:
                    verdict = "PARTIAL"

                desc = result.desc
                result = f"{verdict} ({points}/{self.points})"
                if desc:
                    result += f": {desc}"

        except Exception as e:
            result = traceback.format_exception(e)
            print(f"Exception in {self.func.__name__}:\n")
            print("\n".join(result) + "\n")

        if VERBOSE:
            if points == self.points:
                print(f"🟢 PASS ({points}/{self.points})")
            elif points == 0:
                print(f"🔴 FAIL ({points}/{self.points})")
            else:
                print(f"🟡 PARTIAL ({points}/{self.points})")
        
        ret.send((points, result))


# init decorator
def init(init_func):
    global INIT
    INIT = init_func
    return init_func


# test decorator
def test(points, timeout=None, desc="", required_files=[], dependencies=[]):
    def wrapper(test_func):
        TESTS[test_func.__name__] = _unit_test(
            test_func, points, timeout, desc, required_files, dependencies)

    return wrapper

# debug dir decorator


def debug(debug_func):
    global DEBUG
    DEBUG = debug_func
    return debug_func

# cleanup decorator


def cleanup(cleanup_func):
    global CLEANUP
    CLEANUP = cleanup_func
    return cleanup_func


# lists all tests
def list_tests():
    for test_name, test in TESTS.items():
        print(f"{test_name}({test.points}): {test.desc}")


# run all tests
def run_tests():
    results = {
        "score": 0,
        "full_score": 0,
        "tests": {},
    }

    for test_name, test in TESTS.items():
        if VERBOSE:
            print(f"===== Running {test_name} =====")

        results["full_score"] += test.points

        ret_send, ret_recv = multiprocessing.Pipe()
        proc = multiprocessing.Process(target=test.run, args=(ret_send,))
        proc.start()
        proc.join(test.timeout)
        if proc.is_alive():
            proc.terminate()
            points = 0
            result = "Timeout"
        else:
            (points, result) = ret_recv.recv()

        results["score"] += points
        results["tests"][test_name] = result

        if points == test.points:
            PASSED_TESTS.add(test_name)

    assert results["score"] <= results["full_score"]
    if VERBOSE:
        print("===== Final Score =====")
        print(json.dumps(results, indent=4))
        print("=======================")
    # and results['score'] != results["full_score"]
    if DEBUG and GO_FOR_DEBUG:
        DEBUG()
    # cleanup code after all tests run
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return results


# save the result as json
def save_results(results):
    output_file = f"{TEST_DIR}/score.json"
    print(f"Output written to: {output_file}")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)


def tester_main():
    global VERBOSE, TEST_DIR, GO_FOR_DEBUG

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--dir", type=str, default=".", help="path to your repository"
    )
    parser.add_argument("-l", "--list", action="store_true",
                        help="list all tests")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-g", "--debug", action="store_true",
                        help="create a debug directory with the files used while testing")
    args = parser.parse_args()

    if args.list:
        list_tests()
        return

    VERBOSE = args.verbose
    GO_FOR_DEBUG = args.debug
    test_dir = args.dir
    if not os.path.isdir(test_dir):
        print("invalid path")
        return
    TEST_DIR = os.path.abspath(test_dir)

    # make a copy of the code
    def ignore(_dir_name, _dir_content): return [
        ".git", ".github", "__pycache__", ".gitignore", "*.pyc"]
    shutil.copytree(src=TEST_DIR, dst=TMP_DIR, dirs_exist_ok=True, ignore=ignore)

    if CLEANUP:
        CLEANUP()

    os.chdir(TMP_DIR)

    # run init
    if INIT:
        INIT()

    # run tests
    results = run_tests()
    save_results(results)

    # run cleanup
    if CLEANUP:
        CLEANUP()


# ============= end of legacy code =============
# ============= docker code =============

def stop_cluster():
    subprocess.run(["docker", "compose", "down"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[CLEANUP] Stopping cluster.")


def stop_all_containers():
    container_ids = subprocess.run(
        ["docker", "ps", "-aq"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    ).stdout.decode('utf-8').strip()

    if container_ids:
        # Stop the containers if any are running
        stop_command = ["docker", "stop"] + container_ids.split()
        result = subprocess.run(
            stop_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_remove_all_containers():
    container_ids = subprocess.run(
        ["docker", "ps", "-aq"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    ).stdout.decode('utf-8').strip()

    if container_ids:
        # Stop the containers if any are running
        stop_command = ["docker", "stop"] + container_ids.split()
        result = subprocess.run(
            stop_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Remove the containers
        rm_command = ["docker", "rm"] + container_ids.split()
        result = subprocess.run(
            rm_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[CLEANUP] Removing containers.")


def stop_remove_container(container_name):
    subprocess.run(["docker", "stop", container_name],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "rm", container_name],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[CLEANUP] Removing container '{container_name}'.")


def remove_network(network):
    subprocess.run(["docker", "network", "rm", network],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[CLEANUP] Removing network '{network}'.")


def create_network(network):
    subprocess.run(["docker", "network", "create", network],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Created network '{network}'")


def docker_prune():
    subprocess.run(["docker", "system", "prune", "-af"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Cleaned up docker system.")


def is_container_running(container_name):
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter",
                f"name={container_name}", "--format", "{{.Names}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        running_containers = result.stdout.strip().splitlines()
        if container_name in running_containers:
            return True
        else:
            return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking container status: {e.stderr}")
        return False

# ============= end of docker code =============
# ============= start of autograde.py =============

VENV = "venv_auto"
CONTAINER = "p3_auto"
NUM_ROWS = 100
COLUMNS = ['a', 'b', 'c', 'd']
COLUMNS_SUM = dict()
CSV_FILE = "complex.csv"
PYTHON = f"{VENV}/bin/python3"


@cleanup
def _cleanup(*args, **kwargs):
    stop_all_containers()
    docker_prune()


@init
def _init():
    subprocess.run(["python3", "-m", "venv", VENV], check=True)
    # grpcio==1.66.1 grpcio-tools==1.66.1 numpy==2.1.1 protobuf==5.27.2 pyarrow==17.0.0 setuptools==75.1.0
    subprocess.run([
        f"{VENV}/bin/pip3", "install",
        "grpcio==1.66.1",
        "grpcio-tools==1.66.1", 
        "numpy==2.1.1", 
        "protobuf==5.27.2", 
        "pyarrow==17.0.0", 
        "setuptools==75.1.0"
    ], check=True)

    # create a csv file
    with open(f'{CSV_FILE}', 'w') as f:
        # header
        f.write(",".join(COLUMNS) + "\n")
        # rows
        for i in range(NUM_ROWS):
            values = []
            for j in range(len(COLUMNS)):
                values.append(str(i**j))
            f.write(",".join(values) + "\n")

    # copy to main directory
    shutil.copy(f'{CSV_FILE}', f'{TEST_DIR}/{CSV_FILE}')

    for j, c in enumerate(COLUMNS):
        COLUMNS_SUM[c] = sum([i**j for i in range(NUM_ROWS)])


@test(5, required_files=["Dockerfile"], timeout=600)
def docker_build():
    # testing if the Dockerfile can be built
    # docker build . -t p3
    environment = os.environ.copy()
    environment["DOCKER_CLI_HINTS"] = "false"
    subprocess.check_output(
        ["docker", "build", ".", "-t", "p3"], env=environment)
    

@test(5, dependencies=["docker_build"])
def docker_run():
    # testing if the Docker container can run
    # docker run -d -m 512m -p 127.0.0.1:5440:5440 p3
    subprocess.run(["docker", "run", "-d", "-m", "512m", "-p", "127.0.0.1:5440:5440", "--name", CONTAINER, "p3"], check=True)
    time.sleep(5)
    for _ in range(10):
        if is_container_running(CONTAINER):
            return None
        time.sleep(5)
    return "Container did not start"


@test(10, dependencies=["docker_run"], timeout=300)
def upload_test():
    # testing if the upload.py script can run

    # check if the server is running
    if not is_container_running(CONTAINER):
        return "Server is not running"

    upload_output = subprocess.check_output([PYTHON, "upload.py", "simple.csv"])
    upload_output = upload_output.decode("utf-8")
    if "success" not in upload_output:
        return f"Upload failed. upload.py output: {upload_output}"
    print('uploaded simple.csv')

    # upload the new csv file
    upload1_output = subprocess.check_output([PYTHON, "upload.py", CSV_FILE])
    upload1_output = upload1_output.decode("utf-8")
    if "success" not in upload1_output:
        return f"Upload failed. upload.py output: {upload1_output}"
    print(f'uploaded {CSV_FILE}')
    
    # upload the csv file again
    upload2_output = subprocess.check_output([PYTHON, "upload.py", CSV_FILE])
    upload2_output = upload2_output.decode("utf-8")
    if "success" not in upload2_output:
        return f"Upload failed. upload.py output: {upload2_output}"
    print(f'uploaded {CSV_FILE} again')
    

@test(10, dependencies=["upload_test"], timeout=300)
def csvsum_test():
    # testing if the csvsum.py script can return true sum
    # the sum should be twice the true sum in the new csv file
    
    col = 'c'
    csvsum_output = subprocess.check_output([PYTHON, "csvsum.py", col])
    csvsum_output = csvsum_output.decode("utf-8")
    last_line = csvsum_output.strip().split("\n")[-1]
    int_last_line = int(last_line)

    true_sum = COLUMNS_SUM[col] * 2
    if int_last_line != true_sum:
        return f"For column {col}, expected sum of {true_sum}, got {int_last_line}"
    

@test(10, dependencies=["upload_test"], timeout=300)
def parquetsum_test():
    # testing if the parquetsum.py script can return true sum

    col = 'b'
    parquetsum_output = subprocess.check_output([PYTHON, "parquetsum.py", col])
    parquetsum_output = parquetsum_output.decode("utf-8")
    last_line = parquetsum_output.strip().split("\n")[-1]
    int_last_line = int(last_line)

    true_sum = COLUMNS_SUM[col] * 2
    if int_last_line != true_sum:
        return f"For column {col}, expected sum of {true_sum}, got {int_last_line}"
    
    
@test(15, dependencies=["upload_test"], timeout=2400)
def big_upload():
    # testing if the bigdata.py script can run

    print('uploading big data. this may take a while...')
    bigdata_output = subprocess.check_output([PYTHON, "bigdata.py"])
    bigdata_output = bigdata_output.decode("utf-8")

    if "uploaded" not in bigdata_output:
        return f"Big upload failed. bigdata.py output: {bigdata_output}"


@test(20, dependencies=["big_upload"], timeout=2400)
def big_sum():
    # testing if csv and parquet sum are correct for big data
    # also testing if parquet sum is faster than csv sum

    col = 'z'
    true_sum = 19999950000009

    # sum check
    parquetsum_output = subprocess.check_output([PYTHON, "parquetsum.py", col])
    parquetsum_output = parquetsum_output.decode("utf-8")
    parquetsum = int(parquetsum_output.strip().split("\n")[-1])
    if parquetsum != true_sum:
        return f"For column {col}, expected parquetsum of {true_sum}, got {parquetsum}"

    csvsum_output = subprocess.check_output([PYTHON, "csvsum.py", col])
    csvsum_output = csvsum_output.decode("utf-8")
    csvsum = int(csvsum_output.strip().split("\n")[-1])
    if csvsum != true_sum:
        return f"For column {col}, expected csvsum of {true_sum}, got {csvsum}"
    

    # time check
    parquet_ms = float(parquetsum_output.strip().split("\n")[-2].split()[0])
    csv_ms = float(csvsum_output.strip().split("\n")[-2].split()[0])
    ms_ratio = csv_ms / parquet_ms

    print(f"csv: {csv_ms} ms, parquet: {parquet_ms} ms, ratio: {ms_ratio:.2f}")

    if ms_ratio < 2:
        print('🟡 Warning: Parquet sum should be significantly faster.')
        print('It may be due to reading the whole parquet file rather than a single column.')
        print('Ignore the warning if you have avoided that.')

if __name__ == "__main__":
    tester_main()
