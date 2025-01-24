# ============= legacy code: tester.py =============
from collections import OrderedDict
import json
import os
import traceback
import shutil
import multiprocessing
import glob

multiprocessing.set_start_method("fork")


def warn(msg):
    print(f"🟡 Warning: {msg}")


def error(msg):
    print(f"🔴 Error: {msg}")


ARGS = None

DEBUG = False
VERBOSE = False

TMP_DIR = "/tmp/_cs544_tester_directory"
TEST_DIR = None
DEBUG_DIR = "_autograder_results"
AUTONB_DIR = "_autograder_nb"

# full list of tests
INIT = None
TESTS = OrderedDict()
CLEANUP = None


def verbose(msg):
    if VERBOSE:
        print(msg)


def run_with_timeout(func, timeout):
    def wrapper(ret):
        try:
            func()
            result = None
        except Exception as e:
            result = traceback.format_exception(e)
        ret.send(result)

    ret_send, ret_recv = multiprocessing.Pipe()
    proc = multiprocessing.Process(target=wrapper, args=(ret_send,))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        result = "Timeout"
    else:
        result = ret_recv.recv()
    return result


# dataclass for storing test object info
class _unit_test:
    def __init__(self, func, points, timeout, desc):
        self.func = func
        self.points = points
        self.timeout = timeout
        self.desc = desc

    def run(self, ret):
        points = 0

        try:
            result = self.func()
            if not result:
                points = self.points
                result = f"PASS ({self.points}/{self.points})"
            else:
                print(f"Test {self.func.__name__} failed:\n")
                if isinstance(result, str):
                    result = result.split("\n")
                if isinstance(result, list):
                    print("\n".join(result) + "\n")
                else:
                    print(result + "\n")
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
def test(points, timeout=None, desc=""):
    def wrapper(test_func):
        TESTS[test_func.__name__] = _unit_test(test_func, points, timeout, desc)

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


# get arguments
def get_args():
    return ARGS


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
            print(f"===== Running Test {test_name} =====")

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

        if VERBOSE:
            print(result)
        results["score"] += points
        results["tests"][test_name] = result

    assert results["score"] <= results["full_score"]
    if VERBOSE:
        print("===== Final Score =====")
        print(json.dumps(results, indent=4))
        print("=======================")

    if DEBUG:
        debug_abs_path = f"{TEST_DIR}/{DEBUG_DIR}"
        shutil.rmtree(debug_abs_path, ignore_errors=True)
        shutil.copytree(src=TMP_DIR, dst=debug_abs_path, dirs_exist_ok=True)
        print(f"Run results are stored to {debug_abs_path}")

    # copying the notebooks with autograder outputs
    notebooks = glob.glob(f"{TMP_DIR}/nb/tester-*.ipynb")
    # shutil.rmtree(f"{TEST_DIR}/{AUTONB_DIR}", ignore_errors=True)
    os.makedirs(f"{TEST_DIR}/{AUTONB_DIR}", exist_ok=True)
    for notebook in notebooks:
        shutil.copy(notebook, f"{TEST_DIR}/{AUTONB_DIR}")

    # cleanup code after all tests run
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return results


# save the result as json
def save_results(results):
    output_file = f"{TEST_DIR}/score.json"
    print(f"Output written to: {output_file}")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)


def check_files(test_dir, required_files):
    if not os.path.isdir(f"{test_dir}/.git"):
        warn(f"{test_dir} is not a repository")

    missing_files = []
    for file in required_files:
        if not os.path.exists(f"{test_dir}/{file}"):
            missing_files.append(file)
    if len(missing_files) > 0:
        msg = ", ".join(missing_files)
        warn(f"the following required files are missing: {msg}")


def tester_main(parser, required_files=[]):
    global ARGS, VERBOSE, TEST_DIR, DEBUG

    parser.add_argument(
        "-d", "--dir", type=str, default=".", help="path to your repository"
    )
    parser.add_argument("-l", "--list", action="store_true", help="list all tests")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "-g",
        "--debug",
        action="store_true",
        help="create a debug directory with the files used while testing",
    )
    args = parser.parse_args()

    ARGS = args

    if args.list:
        list_tests()
        return

    VERBOSE = args.verbose
    DEBUG = args.debug
    test_dir = args.dir
    if not os.path.isdir(test_dir):
        error("invalid path")
        return
    TEST_DIR = os.path.abspath(test_dir)

    # check if required files are present
    check_files(test_dir, required_files)

    # clean TMP directory
    shutil.rmtree(TMP_DIR, ignore_errors=True)

    # make a copy of the code
    def ignore(_dir_name, _dir_content):
        return [".git", ".github", "__pycache__", ".gitignore", "*.pyc", DEBUG_DIR]

    shutil.copytree(src=TEST_DIR, dst=TMP_DIR, dirs_exist_ok=True, ignore=ignore)
    os.chdir(TMP_DIR)

    # run init
    if INIT:
        ret = INIT()
        if ret != None:
            result = f"Init failed: {ret}"
            error(result)
            save_results(result)
            exit(-1)

    # run tests
    results = run_tests()
    save_results(results)

    # run cleanup
    if CLEANUP:
        print('Cleaning...')
        ret = CLEANUP()
        if ret != None:
            result = f"Cleanup failed: {ret}"
            error(result)
            exit(-1)


# ============= end of legacy code =============

# ============= start of autograde.py =============


import os, json, time, re
import subprocess
from subprocess import check_output
from subprocess import Popen, PIPE
from pathlib import Path
import traceback
from argparse import ArgumentParser


# key=num, val=answer (as string)
ANSWERS = {}


def run_command(command, timeout_val=None, throw_on_err=True, debug=False):
    command_to_run = command.split(" ")

    std_out, std_err = None, None
    try:
        result = subprocess.run(
            command_to_run, timeout=timeout_val, capture_output=True, text=True
        )
        if debug:
            print("Command", command, "exited with code", result.returncode)

        if result.returncode != 0:
            std_err = (
                "Command " + command + " exited with code " + str(result.returncode)
            )
            std_err += (
                " due to error " + result.stderr + " and standard out " + result.stdout
            )
        else:
            std_out = result.stdout.strip()
    except Exception as e:
        std_err = "Failed to run command " + str(command) + " due to error: " + str(e)

    if throw_on_err and std_err is not None and len(std_err) > 0:
        raise Exception(std_err)

    return std_out, std_err


def get_notebook_container():
    std_out, _ = run_command("docker ps", timeout_val=20)
    for line in std_out.splitlines():
        if "5000->5000" in line:
            container_name = line.split()[-1]
            return container_name
    


def perform_startup(
    startup_timeout=400, command_timeout=20, bootup_buffer=60, debug=False
):
    docker_reset()

    try:
        check_output("docker build . -f hdfs.Dockerfile -t p4-hdfs", shell=True)
        check_output("docker build . -f namenode.Dockerfile -t p4-nn", shell=True)
        check_output("docker build . -f datanode.Dockerfile -t p4-dn", shell=True)
        check_output("docker build . -f notebook.Dockerfile -t p4-nb", shell=True)

        # Start them using docker-compose up
        if debug:
            print("Starting all the containers")
        std_out, _ = run_command(
            "docker compose up -d", timeout_val=startup_timeout, debug=debug
        )

        # Get the notebook container
        # std_out, _ = run_command("docker ps", timeout_val=command_timeout)
        # specs_df = pd.read_csv(
        #     StringIO(std_out), sep="\\s{2,}", engine="python", header=0
        # )
        # specs_df = specs_df[specs_df["PORTS"].str.contains("5000->5000")]
        # nb_container_name = specs_df.iloc[0]["NAMES"]
        nb_container_name = get_notebook_container()
        if nb_container_name is None:
            raise Exception("Notebook container not found")
        if debug:
            print("Got notebook container of", nb_container_name)

        return nb_container_name
    except Exception as e:
        print("An exception occurred while building their dockerfiles", e)
        traceback.print_exc()
        return "Error"


def docker_reset():
    try:
        subprocess.run(["docker compose kill; docker compose rm -f"], shell=True)
        subprocess.run(["docker", "rmi", "-f", "p4-nb"], check=True, shell=False)
        subprocess.run(["docker", "rmi", "-f", "p4-nn"], check=True, shell=False)
        subprocess.run(["docker", "rmi", "-f", "p4-dn"], check=True, shell=False)
        subprocess.run(["docker", "rmi", "-f", "p4-hdfs"], check=True, shell=False)

        result = subprocess.run(
            [
                "docker",
                "container",
                "ls",
            ],
            capture_output=True,
            check=True,
            shell=False,
        )
        if result.stdout.decode("utf-8").count("\n") > 1:
            subprocess.run(["docker stop $(docker ps -q)"], check=True, shell=True)
    except Exception as ex:
        pass


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
    
def list_containers():
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip().splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Error listing containers: {e.stderr}")
        return []


def stop_container(container_name):
    try:
        result = subprocess.run(
            ["docker", "stop", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error stopping container {container_name}: {result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"Error stopping container: {e.stderr}")


# def num_unique_dn(nb_container_name, file):
#     filepath = f"hdfs://boss:9000/{file}"
#     fsck_cmd = f"docker exec {nb_container_name} hdfs fsck {filepath} -files -blocks -locations"
#     output = check_output(fsck_cmd, shell=True).decode("utf-8")
#     num_datanodes = 0
#     for line in output.splitlines():
#         if "Number of data-nodes" in line:
#             num_datanodes = int(line.split(":")[1].strip())
#             break
#     return num_datanodes 


def run_student_code():
    nb_container_name = perform_startup(debug=True)
    file_dir = os.path.abspath(__file__)
    tester_dir = os.path.dirname(file_dir)
    path, _ = run_command("pwd")

    # for a later test

    print("\n" + "=" * 70)
    print("Waiting for HDFS cluster to stabilize... this may take a while")
    print("=" * 70)
    cmd = f"docker exec {nb_container_name} hdfs dfsadmin -fs hdfs://boss:9000 -report"
    print(cmd)
    for i in range(300):
        try:
            output = check_output(cmd, shell=True)
            m = re.search(r"Live datanodes \((\d+)\)", str(output, "utf-8"))
            if not m:
                print("report didn't describe live datanodes")
            else:
                count = int(m.group(1))
                print(f"found {count} live DataNodes")
                if count >= 2:
                    print("cluster is ready")
                    break
        except subprocess.CalledProcessError as e:
            print("couldn't get report from NameNode")
        time.sleep(1)

    print("\n" + "=" * 70)
    print("Running p4a.ipynb notebook... this will take a while")
    print("=" * 70)
    cmd = (
        f"docker exec {nb_container_name} sh -c '"
        + "export CLASSPATH=`$HADOOP_HOME/bin/hdfs classpath --glob` && "
        + "python3 -m nbconvert --execute --to notebook "
        + "nb/p4a.ipynb --output tester-p4a.ipynb'"
    )
    print(cmd)
    try:
        check_output(cmd, shell=True)
    except Exception as e:
        print("An exception occurred while executing p4b.ipynb:", e)
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("Killing worker 1")
    print("=" * 70)

    # import docker

    # client = docker.from_env()
    # containers = client.containers.list()
    # for container in containers:
    #     if "dn-1" in container.name:
    #         print(f"stop {container.name}")
    #         container.stop()
    #         break
    # else:
    #     raise Exception("could not find worker to kill")

    running_containers = list_containers()
    for container in running_containers:
        if "dn-1" in container:
            print(f"stop {container}")
            stop_container(container)
            break
    
    time.sleep(1)
    if not is_container_running("dn-1"):
        print("Worker 1 killed")
    else:
        raise Exception("could not kill worker 1")

    print("\n" + "=" * 70)
    print("Waiting for NameNode to detect DataNode is dead... this may take a while")
    print("=" * 70)
    cmd = f"docker exec {nb_container_name} hdfs dfsadmin -fs hdfs://boss:9000 -report"
    print(cmd)
    for i in range(60):
        try:
            output = check_output(cmd, shell=True)
            m = re.search(r"Live datanodes \((\d+)\)", str(output, "utf-8"))
            if not m:
                print("report didn't describe live datanodes")
            else:
                count = int(m.group(1))
                print(f"NameNode thinks there are {count} live DataNodes")
                if count < 2:
                    print("DataNode death detected by NameNode")
                    break
        except subprocess.CalledProcessError as e:
            print("Couldn't get report from NameNode")
        time.sleep(5)

    # waiting for a little bit more
    time.sleep(5)

    print("\n" + "=" * 70)
    print("Running p4b.ipynb notebook... this will take a while")
    time.sleep(15)
    print("=" * 70)
    try:
        cmd = (
            f"docker exec {nb_container_name} sh -c '"
            + "export CLASSPATH=`$HADOOP_HOME/bin/hdfs classpath --glob` && "
            + "python3 -W ignore -m nbconvert --execute --to notebook "
            + "nb/p4b.ipynb --output tester-p4b.ipynb'"
        )
        print(cmd)
        check_output(cmd, shell=True)
    except Exception as e:
        print("An exception occurred while executing p4b.ipynb:", e)
        traceback.print_exc()

    # make all notebooks writable (if only root can, it's a pain to delete/overwrite later)
    cmd = f"docker exec {nb_container_name} sh -c 'chmod o+w nb/*.ipynb'"
    print(cmd)
    check_output(cmd, shell=True)


def extract_notebook_answers(path):
    print(path)
    answers = {}
    with open(path) as f:
        nb = json.load(f)
        cells = nb["cells"]

        for cell in cells:
            if cell["cell_type"] != "code":
                continue
            if not cell["source"]:
                continue
            m = re.match(r"#[qQ](\d+)(.*)", cell["source"][0].strip())
            if not m:
                continue

            # found a answer cell, add its output to list
            qnum = int(m.group(1))
            notes = m.group(2).strip()
            if qnum in answers:
                warn(f"Warning: answer {qnum} repeated!")

            for output in cell["outputs"]:
                if output.get("output_type") == "execute_result":
                    answers[qnum] = "\n".join(output["data"]["text/plain"])
                if output.get("output_type") == "stream":
                    if not qnum in answers:
                        answers[qnum] = "\n".join(output["text"])

    return answers


def extract_student_answers():
    path = Path("nb") / "tester-p4a.ipynb"
    if os.path.exists(path):
        ANSWERS.update(extract_notebook_answers(path))

    path = Path("nb") / "tester-p4b.ipynb"
    if os.path.exists(path):
        ANSWERS.update(extract_notebook_answers(path))


def diagnostic_checks():

    out, _ = run_command("cat /etc/os-release")
    if (
        'VERSION="24.04.1 LTS (Noble Numbat)"' not in out
        and "Ubuntu 24.04.1 LTS" not in out
    ):
        warn("WARNING - you should be using UBUNTU 24.04.1 LTS (Noble Numbat)")

    out, _ = run_command("lscpu")
    if "x86_64" not in out:
        warn("WARNING - are you using an x86 Architecture")
    try:
        out, _ = run_command(
            "wget -q -O - --header Metadata-Flavor:Google metadata/computeMetadata/v1/instance/machine-type"
        )
        if "e2-medium" not in out:
            warn("WARNING - did you switch to an e2-medium machine?")
    except:
        pass


# @debug
# def create_debug_dir():
#     file_dir = os.path.abspath(__file__)
#     tester_dir = os.path.dirname(file_dir)
#     print("tester_dir: ", file_dir)

#     target = f"{tester_dir}/notebooks_from_test/"
#     print("target: ", target)
#     check_output(f"mkdir -p {target}&& cp nb/tester-p4a.ipynb {target} && cp nb/tester-p4b.ipynb {target}", shell=True)


@init
def init(verbose=False, *args, **kwargs):
    run_student_code()
    extract_student_answers()


def check_has_answer(num):
    if not num in ANSWERS:
        raise Exception(f"Answer to question {num} not found")


@test(points=10)
def q1():
    check_has_answer(1)
    if not "Live datanodes (2):" in ANSWERS[1]:
        return "Output does not indicate 2 live datanodes"


@test(points=10)
def q2():
    check_has_answer(2)
    single = False
    double = False
    for line in ANSWERS[2].split("\n"):
        # if "166" in line and "333" not in line and "single" in line:
        if "15.9" in line and "31.7" not in line and "single" in line:
            single = True
        if "15.9" in line and "31.7" in line and "double" in line:
            double = True
    if not single:
        return "Expected a line like '15.9 M  15.9 M  hdfs://boss:9000/single.csv'"
    if not double:
        return "Expected a line like '15.9 M  31.7 M  hdfs://boss:9000/double.csv'"


@test(points=10)
def q3():
    check_has_answer(3)
    d = json.loads(ANSWERS[3])
    if "FileStatus" not in d:
        return 'Expected "FileStatus" in output'
    if "single.csv" not in ANSWERS[3]:
        return 'Expected "single.csv" in output'
    if "double.csv" in ANSWERS[3]:
        return 'Expected "double.csv" in output'


@test(points=10)
def q3():
    check_has_answer(3)
    # single quote => double quote turns Python dict into JSON
    d = json.loads(ANSWERS[3].replace("'", '"'))

    if "FileStatus" not in d:
        return 'Expected "FileStatus" in output'
    if not d["FileStatus"]["blockSize"] == 1048576:
        return "Value of blocksize is not correct"
    if not d["FileStatus"]["length"] == 16642976:
        return "Value of file length is not correct"


@test(points=10)
def q4():
    check_has_answer(4)
    if (
        ":9864/webhdfs/v1/single.parquet?op=OPEN&namenoderpcaddress=boss:9000&offset=0"
        not in ANSWERS[4]
    ):
        return "Unexpected output"


@test(points=10)
def q5():
    check_has_answer(5)
    # single quote => double quote turns Python dict into JSON
    d = json.loads(ANSWERS[5].replace("'", '"'))
    if not len(d) == 2:
        return "Unexpected number of pairs in dictionary."
    if not min(d.values()) > 1:
        return "Unexpected distribution of blocks."

    if not sum(d.values()) == 16:
        return "Unexpected distribution of blocks."


@test(points=10)
def q6():
    check_has_answer(6)
    # single quote => double quote turns Python dict into JSON
    d = json.loads(ANSWERS[6].replace("'", '"'))
    if not len(d) == 2:
        return "Unexpected number of pairs in dictionary."
    if not min(d.values()) > 1:
        return "Unexpected distribution of blocks."

    if not sum(d.values()) == 32:
        return "Unexpected distribution of blocks."


@test(points=10)
def q7():
    check_has_answer(7)
    result = False
    if "204961" in ANSWERS[7]:
        result = True

    if not result:
        return "Expected a outcome including 204961"
    # assert "204961" in ANSWERS[7]


@test(points=10)
def q8():
    check_has_answer(8)
    try:
        float_num = float(ANSWERS[8])
    except ValueError:
        print(f"'{ANSWERS[8]}' can't be converted to float")

    if float_num > 60.0 or float_num < 7.0:
        return "Speedup ratio seems out of range [7, 60]. TA will check code of q8 manually."


@test(points=10)
def q9():
    check_has_answer(9)
    if not "Live datanodes (1):" in ANSWERS[9]:
        return "Output does not indicate 1 live datanodes"


@test(points=10)
def q10():
    check_has_answer(10)
    # single quote => double quote turns Python dict into JSON
    d = int(ANSWERS[10])
    if d <= 1 or d >= 16:
        return "Unexpected value of lost blocks"


if __name__ == "__main__":
    diagnostic_checks()
    parser = ArgumentParser()
    tester_main(
        parser,
        required_files=[
            "nb/p4a.ipynb",
            "nb/p4b.ipynb",
            "datanode.Dockerfile",
            "hdfs.Dockerfile",
            "notebook.Dockerfile",
            "docker-compose.yml",
            "namenode.Dockerfile",
        ],
    )
    docker_reset()
