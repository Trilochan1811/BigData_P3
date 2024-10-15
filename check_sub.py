#!/usr/bin/env python3

import os
import subprocess
import shutil
import sys
from pathlib import Path

def run_command(command):
    """Utility function to run a shell command and return its output."""
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    return result.stdout.strip(), result.returncode

def main():
    # =============== COMMON ===============
    print("This script is aimed to evaluate the submission of the assignment in a fresh environment.")
    print("It will delete existing docker images and containers.")
    print("It will clone the repository, setup files, and run autograder.")
    
    # Confirmation prompt
    proceed = input("Do you want to continue? (y/n) ").strip().lower()
    if proceed != 'y':
        print("Exiting...")
        sys.exit(1)
    
    # Clean up existing docker images and containers
    subprocess.run("docker stop $(docker ps -a -q)", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("docker rm $(docker ps -a -q)", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("docker rmi $(docker images -q)", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("docker system prune -f", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Check if the current directory is a git repository
    _, code = run_command("git rev-parse --is-inside-work-tree")
    if code != 0:
        print("Error: This is not a git repository.")
        sys.exit(1)

    # Check if the current directory is the root of the git repository
    if not Path('.git').exists():
        print("Error: This is not the root directory of the git repository.")
        sys.exit(1)

    # Find the remote URL
    remote_url, _ = run_command("git config --get remote.origin.url")
    if not remote_url:
        print("Error: No remote URL found for this repository.")
        sys.exit(1)

    # Clone the repository to /tmp/submission
    submission_dir = Path("/tmp/submission")
    if submission_dir.exists():
        shutil.rmtree(submission_dir)

    if subprocess.run(f"git clone {remote_url} {submission_dir}", shell=True).returncode != 0:
        print("Error: Failed to clone the repository.")
        sys.exit(1)

    os.chdir(submission_dir)

    print('---- Checking Authors ----')
    # Find all unique authors
    authors, _ = run_command("git log --format='%aN' | sort -u")

    # remove bot authors
    authors = authors.splitlines()
    authors = [author.strip() for author in authors]
    authors = [author for author in authors if not author.endswith('_appscript')]
    print(f"Authors: {authors}")
    
    # Find expected authors
    num_authors = len(authors)
    repo_name, _ = run_command("basename $(git config --get remote.origin.url)")
    print(f"Repository name: {repo_name}")

    # Count expected number of authors based on underscores
    expected_num_authors = repo_name.count("_")
    if num_authors < expected_num_authors:
        print(f"🟡 Warning: expected {expected_num_authors} authors but got {num_authors}")
    print('---------------------------')

    # =============== PROJECT =================
    # Download necessary files
    repo_url = "https://git.doit.wisc.edu/cdis/cs/courses/cs544/f24/main/-/raw/main/p3/"
    files = ["bigdata.py", "csvsum.py", "parquetsum.py", "simple.csv", "upload.py", "autograde.py"]

    for file in files:
        run_command(f"wget {repo_url}{file} -O {file}")

    # Run auto-grade
    subprocess.run(["python3", "-u", "autograde.py", "-v"])

    print(f"\nYou can find the cloned repository in {submission_dir}")

if __name__ == "__main__":
    main()
