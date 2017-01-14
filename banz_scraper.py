# -*- encoding: utf-8 -*-
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
  

"""
import os
import re
import json

import lxml.html
import requests


class BAnzScraper(object):
    BASE_URL = 'https://www.bundesanzeiger.de/ebanzwww/wexsservlet?'
    BASE = 'page.navid=to_official_part&global_data.designmode=eb'
    YEAR = ('page.navid=official_starttoofficial_start_changeyear'
            '&genericsearch_param.year=%s&genericsearch_param.edition='
            '&genericsearch_param.sort_type=')
    LIST = ('genericsearch_param.edition=%s&genericsearch_param.sort_type='
            '&%%28page.navid%%3Dofficial_starttoofficial_start_update%%29='
            'Veröffentlichungen+anzeigen')

    MONTHS = [u'Januar', u'Februar', u'März', u'April', u'Mai', u'Juni', u'Juli',
            u'August', u'September', u'Oktober', u'November', u'Dezember']

    def get(self, url):
        return requests.get(url)

    def scrape(self, low=0, high=10000):
        collection = {}
        years = self.get_years()
        for year in years:
            if not (low <= year <= high):
                continue
            dates = self.get_dates(year)
            for date in dates:
                print year, date
                collection.update(self.get_items(year, date))
        return collection

    def get_years(self):
        url = self.BASE_URL + self.BASE
        response = self.get(url)
        years = []
        root = lxml.html.fromstring(response.text)
        selector = '#td_sub_menu_v li'
        for li in root.cssselect(selector):
            try:
                year = int(li.text_content())
            except ValueError:
                continue
            years.append(year)
        return years

    def get_dates(self, year):
        url = self.BASE_URL + self.YEAR % year
        response = self.get(url)
        dates = []
        root = lxml.html.fromstring(response.text)
        selector = 'select[name="genericsearch_param.edition"] option'
        for option in root.cssselect(selector):
            dates.append((option.attrib['value'], option.text_content().strip()))
        return dates

    def get_items(self, year, date):
        url = self.BASE_URL + self.LIST % date[0]
        response = self.get(url)
        items = {}
        root = lxml.html.fromstring(response.text)
        selector = 'table[summary="Trefferliste"] tr'
        for tr in root.cssselect(selector):
            tds = tr.cssselect('td')
            if len(tds) != 3:
                continue
            public_body = tds[0].text_content().strip()
            link = tds[1].cssselect('a')[0]
            additional = []
            for c in tds[1].getchildren()[1:]:
                if c.tail is not None and c.tail.strip():
                    additional.append(c.tail.strip())
            orig_date = None
            for a in additional:
                match = re.search('[Vv]om (\d+)\. (\w+) (\d{4})', a, re.U)
                if match is not None:
                    day = int(match.group(1))
                    month = self.MONTHS.index(match.group(2)) + 1
                    year = int(match.group(3))
                    orig_date = '%02d.%02d.%d' % (day, month, year)
                    break
            name = link.text_content()[1:]
            name = re.sub('\s+', ' ', name)
            ident = tds[2].text_content().strip()
            items[ident] = {
                'ident': ident,
                'public_body': public_body,
                'name': name,
                'date': date[1],
                'original_date': orig_date,
                'additional': additional
            }
        return items


def main(arguments):
    minyear = arguments['<minyear>'] or 0
    maxyear = arguments['<maxyear>'] or 10000
    minyear = int(minyear)
    maxyear = int(maxyear)
    banz = BAnzScraper()
    data = {}
    if os.path.exists(arguments['<outputfile>']):
        with file(arguments['<outputfile>']) as f:
            data = json.load(f)
    data.update(banz.scrape(minyear, maxyear))
    with file(arguments['<outputfile>'], 'w') as f:
        json.dump(data, f)

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='BAnz-Scraper 0.0.1')
    main(arguments)
