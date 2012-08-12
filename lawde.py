"""LawDe.

Usage:
  lawde.py load [--path=<path>] <law>...
  lawde.py loadall [--path=<path>]
  lawde.py updatelist
  lawde.py -h | --help
  lawde.py --version

Options:
  --path=<path>  Path to laws dir [default: laws].
  -h --help     Show this screen.
  --version     Show version.

"""
import os
import re
from StringIO import StringIO
import json
import shutil

from docopt import docopt
import requests
import zipfile
from xml.dom.minidom import parseString


class Lawde(object):
    BASE_URL = 'http://www.gesetze-im-internet.de'
    LAWLIST_URL = 'https://api.scraperwiki.com/api/1.0/datastore/sqlite?format=json&name=gesetzesliste&query=select+*+from+`swdata`&apikey='
    BASE_PATH = 'laws/'
    INDENT_CHAR = ' '
    INDENT = 2

    def __init__(self, path=BASE_PATH, lawlist='data/laws.json',
                **kwargs):
        self.indent = self.INDENT_CHAR * self.INDENT
        self.path = path
        self.lawlist = lawlist

    def build_zip_url(self, law):
        return '%s/%s/xml.zip' % (self.BASE_URL, law)

    def download_law(self, law):
        res = requests.get(self.build_zip_url(law))
        file('test.zip', 'w').write(res.content)
        try:
            zipf = zipfile.ZipFile(StringIO(res.content))
        except zipfile.BadZipfile:
            print "Removed %s" % law
            self.remove_law(law)
            return None
        return zipf

    def load(self, laws):
        total = float(len(laws))
        for i, law in enumerate(laws):
            if i % 10 == 0:
                print '%d%%' % (i / total * 100)
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
        norm_date_re = re.compile('<norm builddate="\d+"')
        os.makedirs(law_path)
        for name in zipf.namelist():
            if name.endswith('.xml'):
                xml = zipf.open(name).read()
                xml = norm_date_re.sub('<norm', xml)
                dom = parseString(xml)
                xml = dom.toprettyxml(encoding='utf-8',
                    indent=self.indent)
                if not name.startswith('_'):
                    law_filename = os.path.join(law_path, '%s.xml' % law)
                else:
                    law_filename = name
                file(law_filename, 'w').write(xml)
            else:
                zipf.extract(name, law_path)

    def get_all_laws(self):
        return [l['slug'] for l in json.load(file(self.lawlist))]

    def loadall(self):
        self.load(self.get_all_laws())

    def update_list(self):
        res = requests.get(self.LAWLIST_URL)
        file(self.lawlist, 'w').write(res.content)


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
    try:
        arguments = docopt(__doc__, version='LawDe 0.0.1')
        main(arguments)
    except KeyboardInterrupt:
        print '\nAborted'