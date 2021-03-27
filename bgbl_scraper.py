"""BGBl-Scraper.

Usage:
  bgbl_scaper.py <outputfile> [<minyear> [<maxyear>]]
  bgbl_scaper.py -h | --help
  bgbl_scaper.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""
import os
import re
import json
from collections import defaultdict

import lxml.html
import requests


class BGBLScraper(object):
    BASE_URL = 'http://www.bgbl.de/Xaver/'
    START = 'start.xav?startbk=Bundesanzeiger_BGBl'
    BASE_TOC = ('toc.xav?tocf=xaver.component.TOC_0'
                '&tf=xaver.component.Text_0&qmf=&hlf='
                '&bk=Bundesanzeiger_BGBl&dir=center'
                '&start=1&cur=1&op=1')
    MAIN_TOC = ('toc.xav?tocf=xaver.component.TOC_0'
                '&tf=xaver.component.Text_0&qmf=&hlf='
                '&bk=Bundesanzeiger_BGBl&dir=center'
                '&op=%s')
    YEAR_TOC = ('toc.xav?tocf=xaver.component.TOC_0'
                '&tf=xaver.component.Text_0&qmf=&hlf='
                '&bk=Bundesanzeiger_BGBl&dir=center'
                '&op=%(tocid)s&cur=%(tocid)s&start=%(tocid)s')
    TEXT = ('text.xav?tf=xaver.component.Text_0&tocf='
            '&qmf=&hlf=xaver.component.Hitlist_0'
            '&bk=Bundesanzeiger_BGBl&start=%2F%2F*%5B%40node_id%3D%27__docid__%27%5D')

    year_toc = defaultdict(dict)
    year_docs = defaultdict(dict)
    toc = {}

    def __init__(self, part_count=2):
        self.sid = None
        self.part_count = part_count

    def login(self):
        response = requests.get(self.BASE_URL + self.START)
        self.sid = response.headers['XaverSID']

    def sessionify(self, url):
        if not self.sid:
            self.login()
        return '%s&SID=%s' % (url, self.sid)

    def get(self, url):
        while True:
            response = requests.get(self.sessionify(url))
            if 'Session veraltet' in response.text:
                self.sid = None
                continue
            return response

    def scrape(self, low=0, high=10000):
        collection = {}
        self.toc_offsets = self.get_base_toc()
        # import pdb; pdb.set_trace()
        for part in range(1, self.part_count + 1):
            print(part)
            self.get_main_toc(part)
            self.get_all_year_tocs(part, low, high)
            collection.update(self.get_all_tocs(part, low, high))
        return collection

    def parse(self, response):
        response.encoding = 'utf-8'
        html = re.sub('([,\{])(\w+):', '\\1"\\2":', response.text)
        html = json.loads(html)['innerhtml']
        return lxml.html.fromstring(html)

    def get_base_toc(self):
        url = self.BASE_URL + self.BASE_TOC
        response = self.get(url)
        root = self.parse(response)
        selector = 'a.tocEntry'
        toc_offsets = []
        for a in root.cssselect(selector):
            if not 'Bundesgesetzblatt Teil' in a.attrib.get('title', ''):
                continue
            link_href = a.attrib['href']
            match = re.search('tocid=(\d+)&', link_href)
            if match:
                toc_offsets.append(match.group(1))
        return toc_offsets

    def get_main_toc(self, part=1):
        self.get_main_toc_part(part)

    def get_main_toc_part(self, part):
        offset = self.toc_offsets[part - 1]
        url = self.BASE_URL + (self.MAIN_TOC % offset)
        response = self.get(url)
        root = self.parse(response)
        selector = 'a.tocEntry'
        for a in root.cssselect(selector):
            try:
                year = int(a.text_content())
            except ValueError:
                continue
            doc_id = re.search('tocid=(\d+)&', a.attrib['href'])
            if doc_id is not None:
                self.year_toc[part][year] = doc_id.group(1)

    def get_all_year_tocs(self, part=1, low=0, high=10000):
        for year in self.year_toc[part]:
            if not (low <= year <= high):
                continue
            print("Getting Year TOC %d for %d" % (year, part))
            self.get_year_toc(part, year)

    def get_year_toc(self, part, year):
        year_doc_id = self.year_toc[part][year]
        # import pdb; pdb.set_trace()
        url = self.BASE_URL + self.YEAR_TOC % {'tocid': year_doc_id}
        response = self.get(url)
        root = self.parse(response)
        selector = 'a.tocEntry'
        for a in root.cssselect(selector):
            match = re.search('Nr\. (\d+) vom (\d{2}\.\d{2}\.\d{4})',
                              a.text_content())
            if match is None:
                continue
            print(a.text_content())
            number = int(match.group(1))
            date = match.group(2)
            doc_id = re.search('start=%2f%2f\*%5B%40node_id%3D%27(\d+)%27%5D',
                               a.attrib['href'])
            doc_id = doc_id.group(1)
            self.year_docs[part].setdefault(year, {})
            self.year_docs[part][year][number] = {
                'date': date,
                'doc_id': doc_id
            }

    def get_all_tocs(self, part=1, low=0, high=10000):
        collection = {}
        for year in self.year_docs[part]:
            if not (low <= year <= high):
                continue
            for number in self.year_docs[part][year]:
                try:
                    data = self.get_toc(part, year, number)
                    collection['%d_%d_%d' % (part, year, number)] = data
                except:
                    print('%d %d' % (year, number))
                    json.dump(collection, file('temp.json', 'w'))
                    raise
                print('%d %d' % (year, number))
        return collection

    def get_toc(self, part, year, number):
        year_doc = self.year_docs[part][year][number]
        doc_id = year_doc['doc_id']
        url = self.BASE_URL + self.TEXT.replace('__docid__', doc_id)
        response = self.get(url)
        root = self.parse(response)
        toc = []
        for tr in root.cssselect('tr'):
            td = tr.cssselect('td')[1]
            divs = td.cssselect('div')
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
            href = re.sub('SID=[^&]+&', '', href)
            text = divs[2].text_content().strip()
            print(text)
            match = re.search('aus +Nr. +(\d+) +vom +(\d{1,2}\.\d{1,2}\.\d{4}),'
                              ' +Seite *(\d*)\w?\.?$', text)
            page = None
            date = match.group(2)
            if match.group(3):
                page = int(match.group(3))
            kind = 'entry'
            if name in ('Komplette Ausgabe', 'Inhaltsverzeichnis'):
                # FIXME: there are sometimes more meta rows
                kind = 'meta'
            d = {
                'part': part,
                'year': year, 'toc_doc_id': doc_id,
                'number': number, 'date': date,
                'law_date': law_date, 'kind': kind,
                'name': name, 'href': href, 'page': page
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
    if os.path.exists(arguments['<outputfile>']):
        with file(arguments['<outputfile>']) as f:
            data = json.load(f)
    data.update(bgbl.scrape(minyear, maxyear))
    with file(arguments['<outputfile>'], 'w') as f:
        json.dump(data, f)

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='BGBl-Scraper 0.0.1')
    main(arguments)
