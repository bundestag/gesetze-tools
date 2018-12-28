"""LawDe.

Usage:
  lawde.py load [--path=<path>] <law>...
  lawde.py loadall [--path=<path>]
  lawde.py updatelist
  lawde.py -h | --help
  lawde.py --version

Examples:
  lawde.py load kaeaano

Options:
  --path=<path>  Path to laws dir [default: laws].
  -h --help     Show this screen.
  --version     Show version.

Duration Estimates:
  2-4 hours for total download

"""
import datetime
import os
import re
from io import BytesIO
import json
import shutil
import time
import zipfile
from xml.dom.minidom import parseString

from docopt import docopt
import requests


class Lawde(object):
    BASE_URL = 'http://www.gesetze-im-internet.de'
    BASE_PATH = 'laws/'
    INDENT_CHAR = ' '
    INDENT = 2

    def __init__(self, path=BASE_PATH, lawlist='data/laws.json',
                 **kwargs):
        self.indent = self.INDENT_CHAR * self.INDENT
        self.path = path
        self.lawlist = lawlist

    def build_zip_url(self, law):
        url = '%s/%s/xml.zip' % (self.BASE_URL, law)
        return url

    def download_law(self, law):
        tries = 0
        while True:
            try:
                res = requests.get(self.build_zip_url(law))
                with open('test.zip', 'wb') as f:
                    f.write(res.content)
            except Exception as e:
                tries += 1
                print(e)
                if tries > 3:
                    raise e
                else:
                    print("Sleeping %d" % tries * 3)
                    time.sleep(tries * 3)
            else:
                break
        try:
            zipf = zipfile.ZipFile(BytesIO(res.content))
        except zipfile.BadZipfile:
            print("Removed %s" % law)
            self.remove_law(law)
            return None
        return zipf

    def load(self, laws):
        total = float(len(laws))
        ts1 = datetime.datetime.now()
        print "Laws to download: %d" % len(laws)
        for i, law in enumerate(laws):
            if i == 9:
                ts2 = datetime.datetime.now()
                ts_diff = ts2 - ts1
                print "Estimated download time: %d minutes" % ((ts_diff.seconds * len(laws)/10) / 60)
            if i % 10 == 0:
                print '%.1f%%' % (i / total * 100)
            zipfile = self.download_law(law)
            if zipfile is not None:
                self.store(law, zipfile)

    def build_law_path(self, law):
        prefix = law[0]
        return os.path.join(self.path, prefix, law)

    def remove_law(self, law):
        law_path = self.build_law_path(law)
        shutil.rmtree(law_path, ignore_errors=True)

    def store(self, law, zipf):
        self.remove_law(law)
        law_path = self.build_law_path(law)
        # norm_date_re = re.compile('<norm builddate="\d+"')
        os.makedirs(law_path)
        for name in zipf.namelist():
            if name.endswith('.xml'):
                xml = zipf.open(name).read()
                # xml = norm_date_re.sub('<norm', xml.decode('utf-8'))
                dom = parseString(xml.decode('utf-8'))
                xml = dom.toprettyxml(
                    encoding='utf-8',
                    indent=self.indent
                )
                if not name.startswith('_'):
                    law_filename = os.path.join(law_path, '%s.xml' % law)
                else:
                    law_filename = name
                with open(law_filename, 'w') as f:
                    f.write(xml)
            else:
                zipf.extract(name, law_path)

    def get_all_laws(self):
        with open(self.lawlist) as f:
            return [l['slug'] for l in json.load(f)]

    def loadall(self):
        self.load(self.get_all_laws())

    def update_list(self):
        BASE_URL = 'http://www.gesetze-im-internet.de/Teilliste_%s.html'
        CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789'
        # Evil parsing of HTML with regex'
        REGEX = re.compile('href="\./([^\/]+)/index.html"><abbr title="([^"]*)">([^<]+)</abbr>')

        laws = []

        for char in CHARS:
            print("Loading part list %s" % char)
            try:
                response = requests.get(BASE_URL % char.upper())
                html = response.content
            except Exception:
                continue
            html = html.decode('iso-8859-1')
            matches = REGEX.findall(html)
            for match in matches:
                laws.append({
                    'slug': match[0],
                    'name': match[1].replace('&quot;', '"'),
                    'abbreviation': match[2].strip()
                })
        with open(self.lawlist, 'w') as f:
            json.dump(laws, f)


def main(arguments):
    nice_arguments = {}
    for k in arguments:
        if k.startswith('--'):
            nice_arguments[k[2:]] = arguments[k]
        else:
            nice_arguments[k] = arguments[k]
    lawde = Lawde(**nice_arguments)
    if arguments['load']:
        lawde.load(arguments['<law>'])
    elif arguments['loadall']:
        lawde.loadall()
    elif arguments['updatelist']:
        lawde.update_list()


if __name__ == '__main__':
    arguments = docopt(__doc__, version='LawDe 0.0.1')
    main(arguments)
