#!/usr/bin/env python3

import subprocess
import os

from git import Repo
from datetime import datetime

from typing import List

RAW_XML_PATH = "gesetze-xml"
LAWS_PATH = "gesetze"
LAWS_REPOSITORY = "https://github.com/bundestag/gesetze.git"
BANZ_FILE = "data/banz.json"
BGBL_FILE = "data/bgbl.json"

LOG_FILE = open("updatelawsgit.log", "w")

def run_command(command: List[str]) -> None:
    if subprocess.check_call(command, stdout=LOG_FILE) != 0:
        print("Error while executing", command)
        exit(1)

def clone_lawsgit() -> None:
    print("Updating gesetze.git…")

    if not os.path.exists(LAWS_PATH):
        run_command(["git", "clone", LAWS_REPOSITORY, LAWS_PATH])
    else:
        run_command(["git", "-C", LAWS_PATH, "pull"])

def get_latest_year() -> int:
    repo = Repo(LAWS_PATH)
    timestamp = repo.head.commit.committed_date
    date = datetime.fromtimestamp(timestamp)
    return date.year

def generate_index(minyear: int, maxyear: int) -> None:
    print("Looking for law changes…")

    run_command(["./banz_scraper.py", BANZ_FILE, str(minyear), str(maxyear)])

    # TODO add the other indexes here, once they are working

def fetch_raw_xml() -> None:
    print("Downloading new xml from gesetze-im-internet.de…")

    run_command(["./lawde.py", "loadall", f"--path={RAW_XML_PATH}"])

def convert_markdown() -> None:
    print("Converting new files to markdown…")

    run_command(["./lawdown.py", "convert", RAW_XML_PATH, LAWS_PATH])


def autocommit() -> None:
    print("Creating git commits…")

    run_command(["./lawgit.py", "autocommit", LAWS_PATH])

if __name__ == "__main__":
    clone_lawsgit()
    latest_year = get_latest_year()
    current_year = datetime.now().year
    generate_index(latest_year, current_year)
    fetch_raw_xml()
    convert_markdown()
    autocommit()
