#!/usr/bin/env python3

"""BGBl-Scraper.

Usage:
  bgbl_scaper.py <outputfile> [<minyear> [<maxyear>]]
  bgbl_scaper.py -h | --help
  bgbl_scaper.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

Examples:
  bgbl_scaper.py data/bgbl.json

"""
import sys
from pathlib import Path
import urllib.parse
import re
import json
from collections import defaultdict
import time
import roman_numbers

import lxml.html
from lxml.cssselect import CSSSelector
import requests

from typing import List


class BGBLScraper:
    BASE_URL = 'http://www.bgbl.de/xaver/bgbl/'

    def __init__(self):
        self.session = requests.session()
        self.session.get(self.BASE_URL + 'start.xav')  # save cookies

    def downloadUrl(self, file, query={}):
        query['request.preventCache'] = int(time.time()*1000)
        response = self.session.get(f'{self.BASE_URL}{file}?{urllib.parse.urlencode(query)}')
        return response.json()

    def downloadToc(self, toc_id = 0):
        response = self.downloadUrl('ajax.xav', {'q': 'toclevel', 'n': str(toc_id)})
        return response['items'][0]

    def downloadText(self, toc_id, doc_id) -> lxml.html.HtmlElement:
        query = {
            'tf': 'xaver.component.Text_0',
            'hlf': 'xaver.component.Hitlist_0',
            'tocid': str(toc_id),
            'start': f"//*[@node_id='{doc_id}']",
        }
        response = self.downloadUrl('text.xav', query)
        return lxml.html.fromstring(response['innerhtml'])

    def scrape(self, year_low=0, year_high=sys.maxsize):
        self.year_low = year_low
        self.year_high = year_high

        collection = {}
        for part, part_data in self.get_toc().items():
            for year, year_data in part_data.items():
                for number, number_data in year_data.items():
                    items = []
                    for item in number_data:
                        item['part'] = part
                        item['year'] = year
                        item['number'] = number
                        items.append(item)
                    collection[f'{part}_{year}_{number}'] = items
        return collection

    def get_toc(self):
        response = self.downloadToc()
        assert response['l'] == "Bundesgesetzblatt"
        result = {}
        for item in response['c']:
            match = re.match(r'Bundesgesetzblatt Teil ([IVXLCDM]+)', item['l'], re.IGNORECASE)
            if match:
                part = roman_numbers.number(match.group(1))
                print(f"Getting Part TOC {part}")
                result[part] = self.get_part_toc(item['id'])
        return result

    def get_part_toc(self, part_id):
        response = self.downloadToc(part_id)
        assert response['id'] == part_id
        result = {}
        for item in response['c']:
            year = int(item['l'])
            if not (self.year_low <= year <= self.year_high):
                continue
            print(f"Getting Year TOC {year}")
            result[year] = self.get_year_toc(item['id'])
        return result

    def get_year_toc(self, year_id):
        response = self.downloadToc(year_id)
        assert response['id'] == year_id
        result = {}
        for item in response['c']:
            match = re.match(r'Nr\. (\d+) vom (\d{2}\.\d{2}\.\d{4})', item['l'])
            if match:
                number = int(match.group(1))
                date = match.group(2)
                print(f"Getting Number TOC {number} from {date}")
                result[number] = self.get_number_toc(item['id'], item['did'])
        return result

    def get_number_toc(self, number_id, number_did):
        #response = self.downloadToc(number_id)
        root = self.downloadText(number_id, number_did)
        toc = []
        for tr in root.cssselect('tr'):
            td: lxml.html.HtmlElement = tr.cssselect('td')[1]
            divs: List[CSSSelector] = td.cssselect('div')
            law_date = None
            if not len(divs):
                continue
            if len(divs) == 2:
                divs = [None] + divs
            else:
                law_date = divs[0].text_content().strip()

            link = divs[1].cssselect('a')[0]
            name = link.text_content().strip()
            href = link.attrib['href']
            text = divs[2].text_content().strip()
            match = re.search(r'aus +Nr. +(\d+) +vom +(\d{1,2}\.\d{1,2}\.\d{4}),'
                              r' +Seite *(\d*)\w?\.?$', text)
            page = None
            date = match.group(2)
            if match.group(3):
                page = int(match.group(3))
            kind = 'entry'
            if name in ('Komplette Ausgabe', 'Inhaltsverzeichnis'):
                # FIXME: there are sometimes more meta rows
                kind = 'meta'
            d = {
                'kind': kind,
                'date': date,
                'law_date': law_date,
                'name': name,
                'page': page,
                'href': self.BASE_URL + href,
            }
            toc.append(d)
        return toc


def main(arguments):
    minyear = arguments['<minyear>'] or 0
    maxyear = arguments['<maxyear>'] or 10000
    minyear = int(minyear)
    maxyear = int(maxyear)
    bgbl = BGBLScraper()
    data = {}
    if Path(arguments['<outputfile>']).exists():
        with open(arguments['<outputfile>']) as f:
            data = json.load(f)
    data.update(bgbl.scrape(minyear, maxyear))
    with open(arguments['<outputfile>'], 'w', encoding='utf8') as f:
        json.dump(data, f, indent=4, sort_keys=True, ensure_ascii=False)


if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='BGBl-Scraper 0.0.1')
    main(arguments)
