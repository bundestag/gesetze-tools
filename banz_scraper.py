#!/usr/bin/env python3

"""BAnz-Scraper.

Usage:
  banz_scaper.py <outputfile> [<minyear> [<maxyear>]]
  banz_scaper.py -h | --help
  banz_scaper.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

Duration Estimates:
  2-5 minutes per year
  30-75 minutes in total

Examples:
  banz_scaper.py data/banz.json

"""
from pathlib import Path
import re
import json

from bs4 import BeautifulSoup
import requests
import requests.cookies

from typing import List, Optional, Tuple

from requests.models import Response


class BAnzScraper:
    BASE_URL = 'https://www.bundesanzeiger.de/pub/de/'
    SET_YEAR_URL_PART: str

    MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
              'August', 'September', 'Oktober', 'November', 'Dezember']

    SESSION_COOKIES = requests.cookies.RequestsCookieJar()

    def get(self, url):
        return requests.get(url, cookies=self.SESSION_COOKIES)

    def post(self, *args, **kwargs) -> Response:
        return requests.post(*args, **kwargs, cookies=self.SESSION_COOKIES, headers={
            "Referer": "https://www.bundesanzeiger.de/"
        })

    def scrape(self, low=0, high=10000):
        collection = {}
        years = self.get_years()
        for year in years:
            if not (low <= year <= high):
                continue
            dates = self.get_dates(year)
            for date in dates:
                print(year, date)
                collection.update(self.get_items(year, date))
        return collection

    def get_years(self) -> List[int]:
        url = self.BASE_URL + "amtlicher-teil"
        response = self.get(url)
        self.SESSION_COOKIES = response.cookies
        response.cookies
        years = []

        root = BeautifulSoup(response.text, features="lxml")
        self.SET_YEAR_URL_PART = root.find("div", class_="pager_release_year_container").find("form")["action"]

        year_menu = root.find(id="id5")

        for option in year_menu.find_all("option"):
            try:
                year = int(option.string)
            except ValueError:
                continue
            years.append(year)

        return years

    def get_dates(self, year) -> List[Tuple[str, str]]:
        set_year_url = self.BASE_URL + self.SET_YEAR_URL_PART.replace("./", "")
        response = self.post(set_year_url, data={"year": year})

        dates = []
        root = BeautifulSoup(response.text, features="lxml")

        date_menu = root.find(id="id6")
        for option in date_menu.find_all("option"):
            dates.append((option["value"], option.string.strip()))

        return dates

    def get_items(self, year, date: Tuple[str, str]):
        set_date_url = self.BASE_URL + f"amtlicher-teil?&year={year}&edition={date[0]}"
        response = self.get(set_date_url)

        items = {}
        root = BeautifulSoup(response.text, features="lxml")

        results = root.find(class_="result_container")
        rows = results.find_all(class_="row")

        for row in rows:
            if "sticky-top" in row["class"]:
                continue

            print("==========")
            spans = row.find_all("span")
            title_result = row.find(class_="title_result")

            orig_date: Optional[str] = None
            match = re.search(r'[Vv]om: (\d+)\. ([\wä]+) (\d{4})', str(title_result), re.U)
            if match:
                day = int(match.group(1))
                month = self.MONTHS.index(match.group(2)) + 1
                year = int(match.group(3))
                orig_date = '%02d.%02d.%d' % (day, month, year)

            name = spans[0].string
            public_body: str
            if spans[1].string:
                public_body = spans[1].string
            else:
                public_body = spans[1].contents[1].string.replace("\r\n", "")  # Throw away br tag at the beginning

            ident: str
            if spans[2].string:
                ident = spans[2].string
            else:
                ident = spans[2].contents[1].string  # Throw away br tag at the beginning

            items[ident] = {
                'ident': ident,
                'public_body': public_body,
                'name': name,
                'date': date[1],
                'original_date': orig_date,
                'additional': []  # TODO
            }
            print(items[ident])
        return items


def main(arguments):
    minyear = arguments['<minyear>'] or 0
    maxyear = arguments['<maxyear>'] or 10000
    minyear = int(minyear)
    maxyear = int(maxyear)
    banz = BAnzScraper()
    data = {}
    if Path(arguments['<outputfile>']).exists():
        with open(arguments['<outputfile>']) as f:
            data = json.load(f)
    data.update(banz.scrape(minyear, maxyear))
    with open(arguments['<outputfile>'], 'w') as f:
        json.dump(data, f, indent=4)


if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='BAnz-Scraper 0.0.1')
    main(arguments)
