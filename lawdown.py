# -*- coding: utf-8 -*-
"""LawDown - Law To Markdown.

Usage:
  lawdown.py convert --name=<name>
  lawdown.py convert <inputpath> <outputpath>
  lawdown.py -h | --help
  lawdown.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --no-yaml

"""
import os
import sys
import shutil
import re
from glob import glob
from xml import sax
from collections import defaultdict
from textwrap import wrap
from StringIO import StringIO

import yaml


DEFAULT_YAML_HEADER = {
    'layout': 'default'
}


class LawToMarkdown(sax.ContentHandler):
    state = None
    text = ''
    current_text = ''
    indent_by = ' ' * 4
    list_index = ''
    first_meta = True
    ignore_until = None
    indent_level = 0
    in_list_item = 0
    in_list_index = False
    no_tag = True
    last_list_index = None
    entry_count = 0
    footnotes = {}
    current_heading_num = 1
    current_footnote = None
    no_emph_re = [
        re.compile('(\S?|^)([\*_])(\S)'),
        re.compile('([^\\\s])([\*_])(\S?|$)')
    ]
    list_start_re = re.compile('^(\d+)\.')

    def __init__(self, fileout,
            yaml_header=DEFAULT_YAML_HEADER,
            heading_anchor=False,
            orig_slug=None):
        self.fileout = fileout
        self.yaml_header = yaml_header
        self.heading_anchor = heading_anchor
        self.orig_slug = orig_slug

    def out(self, content):
        if isinstance(content, unicode):
            content = content.encode('utf-8')
        self.fileout.write(content)
        return self

    def out_indented(self, content, indent=None):
        if indent is None:
            indent = self.indent_level
        self.out(self.indent_by * indent)
        self.out(content)

    def write(self, content='', nobreak=False):
        self.out(content + (u'\n' if not nobreak else ''))
        return self

    def write_wrapped(self, text, indent=None):
        if indent is None:
            indent = self.indent_level
        first_indent = ''
        if self.last_list_index is not None:
            space_count = max(0, len(self.indent_by) - (len(self.last_list_index) + 1))
            first_indent = ' ' + self.indent_by[0:space_count]
            self.last_list_index = None
        for line in wrap(text):
            if first_indent:
                self.out(first_indent)
            else:
                self.out(self.indent_by * indent)
                line = self.list_start_re.sub('\\1\\.', line)
            first_indent = ''
            self.write(line)

    def flush_text(self):
        if self.text.strip():
            self.write_wrapped(self.text)
        self.text = ''

    def startElement(self, name, attrs):
        name = name.lower()
        self.no_tag = False
        if self.ignore_until is not None:
            return
        if name == 'fnr':
            if not attrs['ID'] in self.footnotes:
                self.footnotes[attrs['ID']] = None
                self.write('[^%s]' % attrs['ID'])
        if name == 'fussnoten':
            self.ignore_until = 'fussnoten'
        if name == "metadaten":
            self.meta = defaultdict(list)
            self.state = 'meta'
            return
        if name == "text":
            self.indent_level = 0
            self.state = 'text'
        if name == 'footnotes':
            self.state = 'footnotes'
        if self.state == 'footnotes':
            if name == 'footnote':
                self.indent_level += 1
                self.current_footnote = attrs['ID']
            return

        self.text += self.current_text
        self.text = self.text.replace('\n', ' ').strip()
        self.current_text = ''

        if name == 'table':
            self.flush_text()
            self.write()
        elif name == 'dl':
            self.flush_text()
            self.write()
            self.indent_level += 1
        elif name == 'row' or name == 'dd':
            if name == 'row':
                self.indent_level += 1
                self.list_index = '*'
                self.write_list_item()
            self.in_list_item += 1
        elif name == 'entry':
            self.indent_level += 1
            self.in_list_item += 1
            self.list_index = '*'
            self.write_list_item()
        elif name == 'img':
            self.flush_text()
            self.out_indented('![%s](%s)' % (attrs.get('ALT', attrs['SRC']), attrs['SRC']))
        elif name == 'dt':
            self.in_list_index = True
        elif name in ('u', 'b', 'f'):
            pass
        else:
            self.flush_text()

    def endElement(self, name):
        name = name.lower()
        self.no_tag = False
        if self.ignore_until is not None:
            if self.ignore_until == name:
                self.ignore_until = None
            return

        if name == 'u':
            self.current_text = u' *%s* ' % self.current_text.strip()
        elif name == 'f':
            self.current_text = u'*'
        elif name == 'b':
            self.current_text = u' **%s** ' % self.current_text.strip()

        self.text += self.current_text
        self.text = self.text.replace('\n', ' ').strip()
        self.current_text = ''

        if name == "metadaten":
            self.state = None
            if self.first_meta:
                self.first_meta = False
                self.write_big_header()
            else:
                self.write_norm_header()
            self.text = ''
            return
        if self.state == 'meta':
            if name == 'enbez' and self.text == u'Inhaltsübersicht':
                self.ignore_until = 'textdaten'
            else:
                self.meta[name].append(self.text)
            self.text = ''
            return
        elif self.state == 'footnotes':
            if name == 'footnote':
                self.flush_text()
                self.indent_level -= 1
            if name == 'footnotes':
                self.state = None
                self.write()
        if self.current_footnote:
            self.out('[^%s]: ' % self.current_footnote)
            self.current_footnote = None

        if self.in_list_index:
            self.list_index += self.text
            self.text = ''
            if name == 'dt':
                if not self.list_index:
                    self.list_index = '*'
                self.write_list_item()
                self.in_list_index = False
            return

        if name == 'br':
            self.text += '\n'
        elif name == 'table':
            self.write()
        elif name == 'dl':
            self.indent_level -= 1
            self.write()
        elif name == 'dd' or name == 'entry':
            self.in_list_item -= 1
            if name == 'entry':
                self.flush_text()
                self.indent_level -= 1
            self.write()
        elif name == 'la' or name == 'row':
            self.flush_text()
            self.write()
            if name == 'row':
                self.indent_level -= 1
                self.in_list_item -= 1
        elif name == 'p':
            self.flush_text()
            self.write()
        elif name == 'title':
            self.text = self.text.replace('\n', ' ')
            self.text = u'## %s' % self.text
            self.flush_text()
            self.write()
        elif name == 'subtitle':
            self.text = self.text.replace('\n', ' ')
            self.text = u'### %s' % self.text
            self.flush_text()
            self.write()

    def characters(self, text):
        if self.ignore_until is not None:
            return
        for no_emph_re in self.no_emph_re:
            text = no_emph_re.sub(r'\1\\\2\3', text)
        self.current_text += text
        self.no_tag = True

    def endDocument(self):
        pass

    def write_list_item(self):
        self.last_list_index = self.list_index
        self.out_indented(self.list_index, indent=self.indent_level - 1)
        self.list_index = ''

    def write_big_header(self):
        self.store_filename(self.meta['jurabk'][0])
        meta = {
            'Title': self.meta['langue'][0],
            'origslug': self.orig_slug,
            'jurabk': self.meta['jurabk'][0],
            'slug': self.filename
        }

        if self.yaml_header:
            meta.update(self.yaml_header)
            self.out(yaml.safe_dump(meta,
                explicit_start=True,
                explicit_end=False,
                allow_unicode=True,
                default_flow_style=False
            ))
            # Blank line ensures meta doesn't become headline
            self.write('\n---')
        else:
            for kv in meta.items():
                self.write('%s: %s' % kv)
        self.write()
        heading = '# %s (%s)' % (self.meta['langue'][0], self.meta['jurabk'][0])
        self.write(heading)
        self.write()
        if 'ausfertigung-datum' in self.meta:
            self.write(u'Ausfertigungsdatum\n:   %s\n' % self.meta['ausfertigung-datum'][0])
        if 'periodikum' in self.meta and 'zitstelle' in self.meta:
            self.write(u'Fundstelle\n:   %s: %s\n' % (
                self.meta['periodikum'][0], self.meta['zitstelle'][0]))

        for text in self.meta.get('standkommentar', []):
            try:
                k, v = text.split(u' durch ', 1)
            except ValueError:
                self.write('Stand: %s' % text)
            else:
                k = k.capitalize()
                self.write(u'%s durch\n:   %s\n' % (k, v))
        self.text = ''

    def write_norm_header(self):
        hn = '#'
        if 'gliederungskennzahl' in self.meta:
            heading_num = len(self.meta['gliederungskennzahl'][0]) / 3 + 1
            self.current_heading_num = heading_num
        else:
            heading_num = self.current_heading_num + 1
        title = ''
        link = ''
        if 'gliederungsbez' in self.meta:
            title = self.meta['gliederungsbez'][0]
            link = title
        if 'gliederungstitel' in self.meta:
            if title:
                title = u'%s - %s' % (title, self.meta['gliederungstitel'][0])
            else:
                title = self.meta['gliederungstitel'][0]
        if 'enbez' in self.meta:
            title = self.meta['enbez'][0]
            link = title
        if 'titel' in self.meta:
            if title:
                title = u'%s %s' % (title, self.meta['titel'][0])
            else:
                title = self.meta['titel'][0]
        if not title:
            return
        hn = hn * min(heading_num, 6)
        if self.heading_anchor:
            if link:
                link = re.sub('\(X+\)', '', link).strip()
                link = link.replace(u'§', 'P')
                link = u' [%s]' % link
        else:
            link = ''
        heading = u'%s %s%s' % (hn, title, link)
        self.write()
        self.write(heading)
        self.write()

    def store_filename(self, abk):
        abk = abk.lower()
        abk = abk.strip()
        replacements = {
            u'ä': u'ae',
            u'ö': u'oe',
            u'ü': u'ue',
            u'ß': u'ss'
        }
        for k, v in replacements.items():
            abk = abk.replace(k, v)
        abk = re.sub('[^\w-]', '_', abk)
        self.filename = abk


def law_to_markdown(filein, fileout=None, name=None):
    ret = False
    if fileout is None:
        fileout = StringIO()
        ret = True
    parser = sax.make_parser()
    if name is None:
        orig_slug = filein.name.split('/')[-1].split('.')[0]
    else:
        orig_slug = name
    handler = LawToMarkdown(fileout, orig_slug=orig_slug)
    parser.setFeature(sax.handler.feature_external_ges, False)
    parser.setContentHandler(handler)
    parser.parse(filein)
    if ret:
        fileout.filename = handler.filename
        return fileout


def main(arguments):
    if arguments['<inputpath>'] is None and arguments['<outputpath>'] is None:
        law_to_markdown(sys.stdin, sys.stdout, name=arguments['--name'])
        return
    paths = set()
    for filename in glob(os.path.join(arguments['<inputpath>'], '*/*/*.xml')):
        inpath = os.path.dirname(os.path.abspath(filename))
        if inpath in paths:
            continue
        paths.add(inpath)
        law_name = inpath.split('/')[-1]
        with file(filename) as infile:
            out = law_to_markdown(infile)
        slug = out.filename
        outpath = os.path.abspath(os.path.join(arguments['<outputpath>'], slug[0], slug))
        print outpath
        assert outpath.count('/') > 2  # um, better be safe
        outfilename = os.path.join(outpath, 'index.md')
        shutil.rmtree(outpath, ignore_errors=True)
        os.makedirs(outpath)
        for part in glob(os.path.join(inpath, '*')):
            if part.endswith('%s.xml' % law_name):
                continue
            part_filename = os.path.basename(part)
            shutil.copy(part, os.path.join(outpath, part_filename))
        with file(outfilename, 'w') as outfile:
            outfile.write(out.getvalue())
        out.close()


if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='LawDown 0.0.1')
    main(arguments)
