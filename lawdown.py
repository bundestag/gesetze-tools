#!/usr/bin/env python3
"""LawDown - Law To Markdown.

Usage:
  lawdown.py convert [options] --name=<name>
  lawdown.py convert [options] <inputpath> <outputpath>
  lawdown.py -h | --help
  lawdown.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --no-yaml     Don't write YAML header.

Examples:
  lawdown.py convert laws laws-md

"""
from pathlib import Path
import sys
import shutil
import re
from xml import sax
from collections import defaultdict
from textwrap import wrap
from io import StringIO
import yaml


DEFAULT_YAML_HEADER = {
    'layout': 'default'
}


class LawToMarkdown(sax.ContentHandler):
    state = [None]
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
    col_num = 0
    table_header = ''
    head_separator = ''
    no_emph_re = [
        re.compile(r'(\S?|^)([\*_])(\S)'),
        re.compile('([^\\\\s])([\\*_])(\\S?|$)')
    ]
    list_start_re = re.compile(r'^(\d+)\.')

    def __init__(self, fileout,
                 yaml_header=DEFAULT_YAML_HEADER,
                 heading_anchor=False,
                 orig_slug=None):
        self.fileout = fileout
        self.yaml_header = yaml_header
        self.heading_anchor = heading_anchor
        self.orig_slug = orig_slug

    def out(self, content):
        self.fileout.write(content)
        return self

    def out_indented(self, content, indent=None):
        if indent is None:
            indent = self.indent_level
        self.out(self.indent_by * indent)
        self.out(content)

    def write(self, content='', custombreaks=False):
        self.out(content + ('\n' if not custombreaks else ''))
        return self

    def write_wrapped(self, text, indent=None, custombreaks=False):
        if indent is None:
            indent = self.indent_level
        first_indent = ''
        if self.last_list_index is not None:
            space_count = max(0, len(self.indent_by) -
                              (len(self.last_list_index) + 1))
            first_indent = f" {self.indent_by[0:space_count]}"
            self.last_list_index = None
        if custombreaks:
            self.out(self.indent_by * indent)
            self.write(text, custombreaks=custombreaks)
        else:
            for line in wrap(text):
                if first_indent:
                    self.out(first_indent)
                else:
                    self.out(self.indent_by * indent)
                    line = self.list_start_re.sub('\\1\\.', line)
                first_indent = ''
                self.write(line)

    def flush_text(self, custombreaks=False):
        if not custombreaks:
            # remove leading spaces from last line (if there are multiple ones)
            blocks = self.text.split('\ ')
            if len(blocks) > 1:
                blocks[-1] = blocks[-1].replace('\ ', ' ').strip()
                # print first block as-is
                self.text = blocks[0]
                self.flush_text(custombreaks=custombreaks)
                # then increase indentation
                if blocks[0] != '':
                    self.write()
                    self.indent_level += 1
                # then print individual blocks with line breaks
                for block in blocks[1:]:
                    self.text = block
                    # might want to print everything but the first indented once
                    self.flush_text(custombreaks=custombreaks)
                    self.write()
                # then reduce the indentation again
                if blocks[0] != '':
                    self.indent_level -= 1
        if self.text.strip():
            self.write_wrapped(self.text, custombreaks=custombreaks)
        self.text = ''

    def startElement(self, name, attrs):
        name = name.lower()
        self.no_tag = False
        if self.ignore_until is not None:
            return
        if name == 'fnr':
            if self.state[-1] == 'meta':
                self.ignore_until = 'fnr'
                return
            else:
                if not attrs['ID'] in self.footnotes:
                    self.footnotes[attrs['ID']] = None
                    self.write(f"[^{attrs['ID']}]")
        if name == 'fussnoten':
            # add a state "kommentar" in which line breaks are not printed?
            # Might be sufficient to do that on end of "kommentar"
            self.ignore_until = 'fussnoten'
        if name == "metadaten":
            self.meta = defaultdict(list)
            self.state.append('meta')
            return
        if name == "text":
            self.indent_level = 0
            self.state.append('text')
        if name == 'footnotes':
            self.state.append('footnotes')
        if self.state[-1] == 'footnotes':
            if name == 'footnote':
                self.indent_level += 1
                self.current_footnote = attrs['ID']
            return

        self.text += self.current_text
        self.current_text = ''

        if name == 'table':
            self.text += ' '
            self.flush_text()
            self.table_header = '| '
            self.state.append('table')
            self.head_separator = '|'
        elif name == 'colspec':
            self.table_header += '      | '
            try:
                if attrs._attrs['align'] == 'center':
                    self.head_separator += ' :---: |'
                elif attrs['align'] == 'justify':
                    # make this left-aligned
                    self.head_separator += ' :---- |'
            except KeyError:
                # No 'align' in colspec
                self.head_separator += ' :---: |'
                # might want to check for centering etc. in colspec via 'attrs'
        elif name == 'thead':
            self.col_num = 0
            self.state.append('thead')
        elif name == 'tbody':
            self.text = self.table_header.replace('\ ', '<br>') + '\n'
            self.flush_text(custombreaks=True)
            self.text = self.head_separator + '\n'
            self.flush_text(custombreaks=True)
            self.state.append('tbody')
        elif name == 'dl':
            # this is a list
            if 'table' not in self.state:
                self.flush_text()
                self.write()
            else:
                self.text += '<br>'
            self.indent_level += 1
            self.state.append('list')
        elif name == 'br':
            if self.state[-1] in ('table', 'theader', 'tbody'):
                pass
                # Don't flush in the end. Might want to move this to the catch-all case at the bottom
        elif name == 'row':
            if self.state[-1] in ('thead'):
                self.col_num = 0
        elif name == 'dd':
            # self.indent_level += 1
            if self.state[-1] == 'have_tick_number':
                self.state.pop()
            else:
                self.list_index = '*'
            self.write_list_item()
            self.in_list_item += 1
        elif name == 'la' and 'table' in self.state:
            self.last_list_index = self.list_index
            self.text += self.list_index + ' '
            self.list_index = ''
        elif name == 'entry':
            if self.state[-1] in ('table', 'tbody'):
                self.current_text = self.current_text.strip() + '| '
            elif self.state[-1] in ('thead'):
                pass
            else:
                self.indent_level += 1
                self.in_list_item += 1
                self.list_index = '*'
                self.write_list_item()
        elif name == 'img':
            if self.state[-1] in ('table', 'theader', 'tbody'):
                self.current_text += f" ![{attrs.get('ALT', attrs['SRC'])}]({attrs['SRC']}) "
            else:
                self.flush_text()
                self.out_indented(f"![{attrs.get('ALT', attrs['SRC'])}]({attrs['SRC']})")
        elif name == 'dt':
            self.state.append('read_list_index')
        elif name in ('u', 'b', 'f', 'sp', 'tgroup', 'quoter'):
            # skip tgroup only in state table?
            pass
            # might also want to skip on 'sp' (spanning rows in a table)
        else: # Not sure whether this case actually helps much. Might get into issues with tags previously not seen...
            if self.state[-1] not in ('table', 'thead', 'tbody'):
                self.flush_text()

    def endElement(self, name):
        name = name.lower()
        self.no_tag = False
        if self.ignore_until is not None:
            if self.ignore_until == name:
                self.ignore_until = None
            return

        if name == 'u':
            self.current_text = f' *{self.current_text.strip()}* '
        elif name == 'f':
            self.current_text = u'*'
        elif name == 'b':
            self.current_text = f' **{self.current_text.strip()}** '

        self.text += self.current_text
        self.current_text = ''

        if name == "metadaten":
            self.state.pop()
            if self.first_meta:
                self.first_meta = False
                self.write_big_header()
            else:
                self.write_norm_header()
            self.text = ''
            return
        if name == 'text':
            self.state.pop()
        if self.state[-1] == 'meta':
            if name == 'enbez' and self.text == 'Inhaltsübersicht':
                self.ignore_until = 'textdaten'
            else:
                self.meta[name].append(self.text)
            self.text = ''
            return
        elif self.state[-1] == 'footnotes':
            if name == 'footnote':
                self.flush_text()
                self.indent_level -= 1
            if name == 'footnotes':
                self.state.pop()
                self.write()
        if self.current_footnote:
            self.out(f'[^{self.current_footnote}]: ')
            self.current_footnote = None

        if self.state[-1] == 'read_list_index':
            # if self.in_list_index: #if self.state[-1] == 'read_list_index':
            self.list_index += self.text
            self.text = ''
            if name == 'dt':
                if not self.list_index:
                    self.list_index = '*'
                if 'table' not in self.state:
                    # only write the new line outside of tables
                    self.write_list_item()
                self.state.pop()
                # self.in_list_index = False
                self.state.append('have_tick_number')
            return

        if name == 'br':
            if self.state[-1] in ('table', 'theader', 'tbody'):
                self.text += ' \ '
            elif self.state[-1] in ('list'):
                pass
            else:
                # blocks = self.text.split(' \ ')
                # if len(blocks) > 1:
                #     blocks[-1] = blocks[-1].replace(' \ ', ' ').strip()
                #     self.text = ' \ '.join(blocks)
                # self.text += ' \ '
                pass
        elif name == 'table':
            self.write()
            self.state.pop()
            # reset this to what it was
        elif name == 'thead':
            # table head ends here
            self.state.pop()
        elif name == 'tbody':
            self.state.pop()
        elif name == 'dl':
            if 'table' not in self.state:
                self.write()
            self.indent_level -= 1
            self.state.pop()
        elif name == 'entry':
            self.col_num += 1
            # cell[0] is before the first pipe, so the first content cell is cell[1]
            if self.state[-1] in ('table', 'tbody'):
                self.text += ' '
            elif self.state[-1] in ('theader'):
                # enter additional information in header cell
                # get all header cells
                cells = self.table_header.split('| ')
                # add information to current one
                cells[self.col_num] = cells[self.col_num].strip() + '\ ' + self.text
                # strip leading \ and spaces
                cells[self.col_num] = cells[self.col_num].strip(' \\') + ' '
                # re-assemble header
                self.table_header = '| '.join(cells)
                self.text = ''
            else:
                self.flush_text()
                self.in_list_item -= 1
                self.flush_text()
                self.indent_level -= 1
                self.write()
        elif name == 'dd':
            if 'table' not in self.state:
                # only do this when not in a table
                self.flush_text()
                self.in_list_item -= 1
                self.write()
            else:
                self.text = self.text
        elif name == 'la':
            if 'table' not in self.state:
                self.text += ' '
                self.flush_text()
            else:
                self.text += '<br>'
        elif name == 'kommentar':
            self.text = self.text.replace('\ ', '')
        elif name == 'row':
            if self.state[-1] in ('table', 'tbody'):
                self.text = self.text.replace('\ ', '<br>') + ' |\n'
                self.flush_text(custombreaks=True)
            elif self.state[-1] in ('thead'):
                self.head_col = 0
        elif name == 'nb':
            self.flush_text()
        elif name == 'p':
            self.text += ' '
            self.flush_text()
            self.write()
        elif name == 'title':
            self.text = self.text.replace('\n', ' ')
            self.text = f'## {self.text}'
            self.flush_text()
            self.write()
        elif name == 'subtitle':
            self.text = self.text.replace('\n', ' ')
            self.text = f'## {self.text}'
            self.flush_text()
            self.write()

    def characters(self, text):
        if self.ignore_until is not None:
            return
        for no_emph_re in self.no_emph_re:
            text = no_emph_re.sub(r'\1\\\2\3', text)
        self.current_text += text.replace('\n', ' ').strip()
        self.no_tag = True

    def endDocument(self):
        pass

    def write_list_item(self):
        self.last_list_index = self.list_index
        # increase_indent = False
        # if len(self.list_index) > 2:
        #     # If there are at least three characters in the list_index (so <number><letter><dot/bracket> is possible)
        #     if self.list_index[-2].isalpha():   # If this there is a letter before the dot/bracket
        #         self.indent_level += 1          # increase indentation
        #         increase_indent = True
        self.out_indented(self.list_index, indent=self.indent_level - 1)
        # if increase_indent:
        #     self.indent_level -= 1              # decrease indentation again
        self.list_index = ''

    def clean_title(self, title):
        title = title.replace(' \\*)', '').strip()
        title = re.sub(r'\\\*', '*', title)
        return title

    def write_big_header(self):
        self.store_filename(self.meta['jurabk'][0])

        title = self.clean_title(self.meta['langue'][0])

        meta = {
            'Title': title,
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
            for k, v in list(meta.items()):
                self.write(f"{k}: {v}")
        self.write()
        heading = f"# {title} ({self.meta['jurabk'][0]})"
        self.write(heading)
        self.write()
        if 'ausfertigung-datum' in self.meta:
            self.write(
                f"Ausfertigungsdatum\n:   {self.meta['ausfertigung-datum'][0]}\n")
        if 'periodikum' in self.meta and 'zitstelle' in self.meta:
            self.write(
                f"Fundstelle\n:   {self.meta['periodikum'][0]}: {self.meta['zitstelle'][0]}\n")

        for text in self.meta.get('standkommentar', []):
            try:
                k, v = text.split(' durch ', 1)
            except ValueError:
                self.write(f'Stand: {text}')
            else:
                k = k.capitalize()
                self.write(f'{k} durch\n:   {v}\n')
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
                title = f"{title} - {self.meta['gliederungstitel'][0]}"
            else:
                title = self.meta['gliederungstitel'][0]
        if 'enbez' in self.meta:
            title = self.meta['enbez'][0]
            link = title
        if 'titel' in self.meta:
            if title: 
                # could also add the "brief" in "br" here
                title = f"{title} {self.meta['titel'][0]}"
            else:
                title = self.meta['titel'][0]
        if not title:
            return
        hn = hn * int(min(heading_num, 6))
        if self.heading_anchor:
            if link:
                link = re.sub(r'\(X+\)', '', link).strip()
                link = link.replace('§', 'P')
                link = f' [{link}]'
        else:
            link = ''
        heading = f'{hn} {title}{link}'
        self.write()
        self.write(heading)
        self.write()

    def store_filename(self, abk):
        abk = abk.lower()
        abk = abk.strip()
        replacements = {
            'ä': 'ae',
            'ö': 'oe',
            'ü': 'ue',
            'ß': 'ss'
        }
        for k, v in list(replacements.items()):
            abk = abk.replace(k, v)
        abk = re.sub(r'[^\w-]', '_', abk)
        self.filename = abk


def law_to_markdown(filein, fileout=None, name=None, yaml_header=True):
    ret = False
    if fileout is None:
        fileout = StringIO()
        ret = True
    parser = sax.make_parser()
    if name is None:
        orig_slug = filein.name.split('/')[-1].split('.')[0]
    else:
        orig_slug = name
    handler = LawToMarkdown(fileout, orig_slug=orig_slug, yaml_header=DEFAULT_YAML_HEADER if yaml_header else None)
    parser.setFeature(sax.handler.feature_external_ges, False)
    parser.setContentHandler(handler)
    parser.parse(filein)
    if ret:
        fileout.filename = handler.filename
        return fileout


def main(arguments):
    if arguments['<inputpath>'] is None and arguments['<outputpath>'] is None:
        with open(arguments['--name']) as infile:
            law_to_markdown(infile, sys.stdout, yaml_header=not arguments['--no-yaml'])
        return
    paths = set()
    for filename in Path(arguments['<inputpath>']).glob('*/*/*.xml'):
        inpath = filename.resolve().parent
        if inpath in paths:
            continue
        paths.add(inpath)
        law_name = inpath.name
        with open(filename, "r") as infile:
            out = law_to_markdown(infile, yaml_header=not arguments['--no-yaml'])
        slug = out.filename
        outpath = (Path(arguments['<outputpath>']) / slug[0] / slug).resolve()
        print(outpath)
        assert len(outpath.parents) > 1  # um, better be safe
        outfilename = outpath / 'index.md'
        shutil.rmtree(outpath, ignore_errors=True)
        outpath.mkdir(parents=True)
        for part in inpath.glob('*'):
            if part.name == f'{law_name}.xml':
                continue
            part_filename = part.name
            shutil.copy(part, outpath / part_filename)
        with open(outfilename, 'w') as outfile:
            outfile.write(out.getvalue())
        out.close()


if __name__ == '__main__':
    from docopt import docopt
    try:
        arguments = docopt(__doc__, version='LawDown 0.0.1')
        main(arguments)
    except KeyboardInterrupt:
        print("\nAbort")
