"""BGBl-Scraper.

Usage:
  bgbl_scaper.py <outputfile> [<minyear> [<maxyear>]]
  bgbl_scaper.py -h | --help
  bgbl_scaper.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""
import re
import json
from collections import defaultdict

import lxml.html
import requests


class BGBLScraper(object):
    BASE_URL = 'http://www.bgbl.de/Xaver/'
    START = 'start.xav?startbk=Bundesanzeiger_BGBl'
    BASE_TOCS = [('toc.xav?dir=center&start=2&cur=2&op=2'
                '&tf=Bundesanzeiger_BGBl_mainFrame'
                '&hlf=Bundesanzeiger_BGBl_mainFrame'
                '&qmf=Bundesanzeiger_BGBl_mainFrame'
                '&tocf=Bundesanzeiger_BGBl_tocFrame'
                '&bk=Bundesanzeiger_BGBl'),
                ('toc.xav?tocf=Bundesanzeiger_BGBl_tocFrame'
                '&tf=Bundesanzeiger_BGBl_mainFrame'
                '&qmf=Bundesanzeiger_BGBl_mainFrame'
                '&hlf=Bundesanzeiger_BGBl_mainFrame&start=2'
                '&bk=Bundesanzeiger_BGBl&dir=down&op=580388&noca=7')
    ]

    YEAR_TOC = ('toc.xav?tocf=Bundesanzeiger_BGBl_tocFrame'
                '&tf=Bundesanzeiger_BGBl_mainFrame'
                '&qmf=Bundesanzeiger_BGBl_mainFrame'
                '&hlf=Bundesanzeiger_BGBl_mainFrame&start=2'
                '&bk=Bundesanzeiger_BGBl&dir=down&op=__docid__&noca=10')

    TEXT = ('text.xav?tocf=Bundesanzeiger_BGBl_tocFrame&'
                'tf=Bundesanzeiger_BGBl_mainFrame'
                '&qmf=Bundesanzeiger_BGBl_mainFrame'
                '&hlf=Bundesanzeiger_BGBl_mainFrame'
                '&start=%2f%2f*%5B%40node_id%3D%27__docid__%27%5D'
                '&bk=Bundesanzeiger_BGBl')

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
        for part in range(1, self.part_count + 1):
            print part
            self.get_main_toc(part)
            self.get_all_year_tocs(part, low, high)
            collection.update(self.get_all_tocs(part, low, high))
        return collection

    def get_main_toc(self, part=1):
        self.get_main_toc_part(part)

    def get_main_toc_part(self, part):
        url = self.BASE_URL + self.BASE_TOCS[part - 1]
        response = self.get(url)
        root = lxml.html.fromstring(response.text)
        selector = '.tocelement a[target="Bundesanzeiger_BGBl_mainFrame"]'
        for a in root.cssselect(selector):
            try:
                year = int(a.text_content())
            except ValueError:
                continue
            doc_id = re.search('start=%2f%2f\*%5B%40node_id%3D%27(\d+)%27%5D',
                               a.attrib['href'])
            if doc_id is not None:
                self.year_toc[part][year] = doc_id.group(1)

    def get_all_year_tocs(self, part=1, low=0, high=10000):
        for year in self.year_toc[part]:
            if not (low <= year <= high):
                continue
            print "Getting Year TOC %d for %d" % (year, part)
            self.get_year_toc(part, year)

    def get_year_toc(self, part, year):
        year_doc_id = self.year_toc[part][year]
        url = self.BASE_URL + self.YEAR_TOC.replace('__docid__', year_doc_id)
        response = self.get(url)
        root = lxml.html.fromstring(response.text)
        selector = '.tocelement a[target="Bundesanzeiger_BGBl_mainFrame"]'
        for a in root.cssselect(selector):
            match = re.search('Nr\. (\d+) vom (\d{2}\.\d{2}\.\d{4})',
                              a.text_content())
            if match is None:
                continue
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
                    print '%d %d' % (year, number)
                    json.dump(collection, file('temp.json', 'w'))
                    raise
                print '%d %d' % (year, number)
        return collection

    def get_toc(self, part, year, number):
        year_doc = self.year_docs[part][year][number]
        doc_id = year_doc['doc_id']
        url = self.BASE_URL + self.TEXT.replace('__docid__', doc_id)
        response = self.get(url)
        root = lxml.html.fromstring(response.text)
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
            print text
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
    with file(arguments['<outputfile>'], 'w') as f:
        json.dump(bgbl.scrape(minyear, maxyear), f)

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='BGBl-Scraper 0.0.1')
    main(arguments)
