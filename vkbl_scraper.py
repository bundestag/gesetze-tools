"""VkBl-Scraper.

Usage:
  vkbl_scaper.py <outputfile> [<minyear> [<maxyear>]]
  vkbl_scaper.py -h | --help
  vkbl_scaper.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.

"""

import re
import os
import json
import time
import datetime
import requests

import lxml.html


def get_url(url):
    response = requests.get(url)
    response.encoding = 'latin1'
    return response.text


def ctext(el):
    result = []
    if el.text:
        result.append(el.text)
    for sel in el:
        if sel.tag in ["br"]:
            result.append(ctext(sel))
            result.append('\n')
        else:
            result.append(ctext(sel))
        if sel.tail:
            result.append(sel.tail)
    return "".join(result)

slugify_re = re.compile('[^a-z]')


def slugify(key):
    return slugify_re.sub('', key.lower())


class VkblScraper:
    URL = 'http://www.verkehr-data.com/docs/artikelsuche.php?seitenzahl=1&anzahl=10000&start=0&Titel=&Datum=&Muster=&Muster2=&Jahrgang=%d&VerordnungsNr=&Seite=&Bereichsname=&DB=&Aktenzeichen='
    PRICE_RE = re.compile(r'Preis: (\d+,\d+) \((\d+) Seite')

    def scrape(self, low=1947, high=datetime.datetime.now().year):
        items = {}
        total_sum = 0
        for year in range(low, high + 1):
            tries = 0
            while True:
                try:
                    response = get_url(self.URL % year)
                except Exception:
                    tries += 1
                    if tries > 10:
                        raise
                    time.sleep(2 * tries)
                    continue
                else:
                    break
            root = lxml.html.fromstring(response)
            total_sum += len(root.cssselect(".tabelle2"))
            print(year, len(root.cssselect(".tabelle2")))
            for i, table in enumerate(root.cssselect(".tabelle2")):
                trs = table.cssselect('tr')
                header = trs[0].cssselect('td')[0].text_content().strip()
                print(i, header)
                try:
                    genre, edition = header.split('\xa0 ')
                    edition = edition.split(' ')[2]
                except ValueError:
                    genre = header
                    edition = ''
                title = ctext(trs[1].cssselect('td')[0]).replace('Titel:', '').strip().splitlines()
                title = [t.strip() for t in title if t.strip()]
                title, description = title[0], '\n'.join(title[1:])
                extra = {}
                for tr in trs[2:]:
                    tds = tr.cssselect('td')
                    if len(tds) == 2:
                        key = tds[0].text_content().replace(':', '').strip()
                        value = tds[1].text_content().strip()
                        extra[slugify(key)] = value
                    elif len(tds) == 1:
                        if tds[0].cssselect('img[src="../images/orange.gif"]'):
                            extra['link'] = tds[0].cssselect('a')[0].attrib['href']
                            extra['vid'] = extra['link'].split('=')[-1]
                            match = self.PRICE_RE.search(tds[0].text_content())
                            extra['price'] = float(match.group(1).replace(',', '.'))
                            extra['pages'] = int(match.group(2))
                data = dict(extra)
                data.update({
                    'genre': genre,
                    'edition': edition,
                    'title': title,
                    'description': description
                })
                ident = '%s.%s.%s.%s' % (
                    data.get('jahr', ''),
                    data.get('vonummer', ''),
                    data.get('seite', ''),
                    data.get('aktenzeichen', '')
                )
                items[ident] = data
        print(total_sum, len(items))
        return items


def main(arguments):
    current_year = datetime.datetime.now().year
    minyear = arguments['<minyear>'] or 1947
    maxyear = arguments['<maxyear>'] or current_year
    minyear = int(minyear)
    maxyear = int(maxyear)
    vkbl = VkblScraper()
    data = {}
    if os.path.exists(arguments['<outputfile>']):
        with file(arguments['<outputfile>']) as f:
            data = json.load(f)
    data.update(vkbl.scrape(minyear, maxyear))
    with file(arguments['<outputfile>'], 'w') as f:
        json.dump(data, f)

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='VkBl-Scraper 0.0.1')
    main(arguments)
