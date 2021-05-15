#!/usr/bin/env python3

"""LawGit - Semi-automatic law change commits.

Usage:
  lawgit.py autocommit <repopath> [--dry-run] [--consider-old] [--grep=<grep>]
  lawgit.py -h | --help
  lawgit.py --version

Options:
  --dry-run         Make a dry run.
  --consider-old    Consider old laws for commits.
  -h --help         Show this screen.
  --version         Show version.

Examples:
  lawgit.py autocommit ../gesetze --dry-run

"""
import re
from pathlib import Path
import json
from datetime import datetime, timedelta
from collections import defaultdict

from git import Repo, Commit, DiffIndex, Diff
from git.exc import GitCommandError

from typing import List, Dict, Tuple


def log(*message: str):
    print(datetime.now(), ":", *message)


class TransientState(Exception):
    pass


class BGBlSource:
    """BGBl as a source for law change"""

    change_re = [
        re.compile(
            r'BGBl +(?P<part>I+):? *(?P<year>\d{4}), +(?:S\. )?(?P<page>\d+)'),
        re.compile(
            r'BGBl +(?P<part>I+):? *(?P<year>\d{4}), \d \((?P<page>\d+)\)'),
        re.compile(r'BGBl +(?P<part>I+):? *(?P<year>\d{4}), (?P<page>\d+)'),
        re.compile(
            r'\d{1,2}\.\.?\d{1,2}\.\.?(?P<year>\d{4}) (?P<part>I+) (?:S\. )?(?P<page>\d+)'),
        re.compile(
            r'(?P<year>\d{4}).{,8}?BGBl\.? +(?P<part>I+):? +(?:S\. )?(?P<page>\d+)'),
        # re.compile(u'Art. \d+ G v. (?P<day>\d{1,2}).(?P<month>\d{1,2}).(?P<year>\d{4})')
    ]

    transient = (
        "noch nicht berücksichtigt",
        "noch nicht abschließend bearbeitet"
    )

    def __init__(self, source):
        self.load(source)

    def __str__(self):
        return self.__class__.__name__

    def load(self, source):
        self.data = {}
        data = json.load(open(source))
        for key, toc_list in data.items():
            for toc in toc_list:
                if toc['kind'] == 'meta':
                    continue
                toc['part_i'] = 'I' * toc['part']
                self.data[(toc['year'], toc['page'], toc['part'])] = toc

    def find_candidates(self, lines: List[str]):
        candidates = []
        for line in lines:
            for c_re in self.change_re:
                for match in c_re.finditer(line):
                    if any(t in line for t in self.transient):
                        raise TransientState
                    matchdict = match.groupdict()
                    if 'page' in matchdict:
                        key = (
                            int(matchdict['year']),
                            int(matchdict['page']),
                            len(matchdict['part'])
                        )
                        if key in self.data:
                            candidates.append(key)
                    # elif 'month' in matchdict:
                    #     for key, toc in self.data.iteritems():
                    #         if toc['date'] == '{day:0>2}.{month:0>2}.{year}'.format(**matchdict):
                    #             candidates.append(key)
        return candidates

    def get_order_key(self, key):
        return self.get_date(key)

    def get_date(self, key):
        bgbl_entry = self.data[key]
        return datetime.strptime(bgbl_entry['date'], '%d.%m.%Y')

    def get_branch_name(self, key):
        bgbl_entry = self.data[key]
        return f"bgbl/{bgbl_entry['year']}/{bgbl_entry['part']}-{bgbl_entry['number']}"

    def get_ident(self, key):
        bgbl_entry = self.data[key]
        return bgbl_entry['href']

    def get_message(self, key):
        bgbl_entry = self.data[key]
        return ('%(name)s\n\n%(date)s: BGBl %(part_i)s: %(year)s, '
                '%(page)s (Nr. %(number)s)' % bgbl_entry)


class BAnzSource:
    """BAnz as a source for law change"""

    def __init__(self, source):
        self.load(source)

    def __str__(self):
        return self.__class__.__name__

    def load(self, source):
        self.data = json.load(open(source))

    def find_candidates(self, lines: List[str]) -> List[str]:
        candidates: List[str] = []
        for line in lines:
            line = re.sub(r'[^\w \.]', '', line)
            line = re.sub(r' \d{4} ', ' ', line)
            for key in self.data:
                if key in line:
                    if "noch nicht berücksichtigt" in line:
                        raise TransientState
                    candidates.append(key)
        return candidates

    def get_order_key(self, key):
        return self.get_date(key)

    def get_date(self, key):
        entry = self.data[key]
        return datetime.strptime(entry['date'], '%d.%m.%Y')

    def get_branch_name(self, key):
        entry = self.data[key]
        date_parts = entry['date'].split('.')
        return f"banz/{date_parts[2]}/{'-'.join(reversed(date_parts[:2]))}"

    def get_ident(self, key):
        return key

    def get_message(self, key):
        entry = dict(self.data[key])
        additional_str = ', '.join(entry['additional'])
        if additional_str:
            entry['additional_str'] = f', {additional_str}'
        else:
            entry['additional_str'] = ''
        return ('%(name)s\n\n%(date)s: %(ident)s, %(public_body)s'
                '%(additional_str)s' % entry)


class VkblSource:
    """VkBl as a source for law change"""

    transient = (
        "noch nicht berücksichtigt",
        "noch nicht abschließend bearbeitet"
    )

    change_re = [
        re.compile(r'VkBl: *(?P<year>\d{4}),? +(?:S\. )?(?P<page>\d+)')
    ]

    def __init__(self, source):
        self.load(source)

    def __str__(self):
        return self.__class__.__name__

    def load(self, source):
        self.data = {}
        data = json.load(open(source))
        for key, value in data.items():
            if value['jahr'] and value['seite']:
                ident = (int(value['jahr']), int(value['seite']))
                value['date'] = value['verffentlichtam']
                self.data[ident] = value

    def find_candidates(self, lines):
        candidates = []
        for line in lines:
            for c_re in self.change_re:
                for match in c_re.finditer(line):
                    if any(t in line for t in self.transient):
                        raise TransientState
                    matchdict = match.groupdict()
                    key = (
                        int(matchdict['year']),
                        int(matchdict['page']),
                    )
                    if key in self.data:
                        candidates.append(key)
        return candidates

    def get_order_key(self, key):
        return self.get_date(key)

    def get_date(self, key):
        entry = self.data[key]
        return datetime.strptime(entry['verffentlichtam'], '%d.%m.%Y')

    def get_branch_name(self, key):
        entry = self.data[key]
        date_parts = entry['verffentlichtam'].split('.')
        return f"vkbl/{date_parts[2]}/{'-'.join(reversed(date_parts[:2]))}"

    def get_ident(self, key):
        return key

    def get_message(self, key):
        """
        {
            u'description': u'',
            u'vid': u'19463',
            u'seite': u'945',
            u'price': 3.4,
            u'edition': u'23/2012',
            u'aufgehobenam': u'',
            'date': u'15.12.2012',
            u'verffentlichtam': u'15.12.2012',
            u'pages': 9,
            u'title': u'Verordnung \xfcber die Betriebszeiten der Schleusen ...',
            u'jahr': u'2012', u'inkraftab': u'01.01.2013',
            u'verkndetam': u'22.11.2012',
            u'link': u'../shop/in_basket.php?vID=19463',
            u'aktenzeichen': u'',
            u'genre': u'Wasserstra\xdfen,
            Schifffahrt',
            u'vonummer': u'215'
        }"
        """
        entry = dict(self.data[key])
        return (f"{entry['title']}\n\n{entry['verkndetam']}: {entry['edition']} S. {entry['seite']} ({entry['vonummer']})")


class LawGit:
    laws = defaultdict(list)
    law_changes: Dict[str, Tuple[bool, str, Path]] = {}
    bgbl_changes = defaultdict(list)

    def __init__(self, path, dry_run=False, consider_old=False, grep=None):
        self.path = Path(path)
        self.dry_run = dry_run
        self.grep = grep
        self.consider_old = consider_old
        self.repo = Repo(path)
        self.sources = [
            BGBlSource('data/bgbl.json'),
            BAnzSource('data/banz.json'),
            VkblSource('data/vkbl.json')
        ]

    def prepare_commits(self):
        branches = defaultdict(dict)
        self.collect_laws()
        for law in self.laws:
            result = self.determine_source(law)
            if result is None:
                continue
            source, key = result
            date = source.get_date(key)
            if not self.consider_old and date + timedelta(days=30 * 12) < datetime.now():
                log(f"Skipped {law} {result} (too old)")
                continue
            branch_name = source.get_branch_name(key)
            ident = source.get_ident(key)
            branches[branch_name].setdefault(ident, [])
            branches[branch_name][ident].append((law, source, key))
        return branches

    def collect_laws(self):
        hcommit: Commit = self.repo.head.commit
        wdiff: DiffIndex = hcommit.diff(None, create_patch=True)

        for diff in wdiff:
            diff: Diff
            if diff.b_blob:
                law_name = diff.b_blob.path.split('/')[1]
                if self.grep and self.grep not in law_name:
                    continue
                filename = '/'.join(diff.b_blob.path.split('/')
                                    [:2] + ['index.md'])
                filename = self.path / filename
                if filename.exists():
                    self.laws[law_name].append(diff.b_blob.path)
                    self.law_changes[law_name] = (
                        False, diff.diff.decode(), filename)
            else:
                log("Found deleted law?")

        for filename in self.repo.untracked_files:
            law_name = filename.split('/')[1]
            if self.grep and self.grep not in law_name:
                continue
            self.laws[law_name].append(filename)
            filename = '/'.join(filename.split('/')[:2] + ['index.md'])
            filename = self.path / filename
            with open(filename) as f:
                self.law_changes[law_name] = (True, f.read(), filename)

    def determine_source(self, law_name):
        new_file, text, filename = self.law_changes[law_name]
        lines: List[str] = [line for line in text.splitlines()]
        candidates = self.find_in_sources(lines)
        if not candidates:
            with open(filename) as f:
                lines = [line for line in f.read().splitlines()]
            candidates.extend(self.find_in_sources(lines))
        if not candidates:
            return None
        return sorted(candidates, key=lambda x: x[0].get_order_key(x[1]))[-1]

    def find_in_sources(self, lines: List[str]):
        candidates = []
        for source in self.sources:
            try:
                candidates.extend([(source, c)
                                   for c in source.find_candidates(lines)])
            except TransientState:
                return []
        return candidates

    def autocommit(self):
        branches = self.prepare_commits()
        for branch in sorted(branches.keys()):
            self.commit_branch(branch, branches[branch])

    def commit_branch(self, branch, commits):
        if not self.dry_run:
            self.repo.git.stash()
        try:
            log(f"git checkout -b {branch}")
            if not self.dry_run:
                self.repo.git.checkout(b=branch)
        except GitCommandError:
            log(f"git checkout {branch}")
            if not self.dry_run:
                self.repo.git.checkout(branch)
        if not self.dry_run:
            self.repo.git.merge('master')
            self.repo.git.stash('pop')
        for ident in commits:
            for law_name, source, key in commits[ident]:
                for filename in self.laws[law_name]:
                    if (self.path / filename).exists():
                        log(f"git add {filename}")
                        if not self.dry_run:
                            self.repo.index.add([str(filename)])
                    else:
                        log(f"git rm {str(filename)}")
                        self.repo.index.remove([str(filename)])
            msg = source.get_message(key)
            
            log(f'git commit -m"{msg}"')
            if not self.dry_run:
                self.repo.index.commit(msg)
            log("")
        log("git checkout master")
        if not self.dry_run:
            self.repo.heads.master.checkout()
        log(f"git merge {branch} --no-ff")
        if not self.dry_run:
            self.repo.git.merge(branch, no_ff=True)


def main(arguments):
    kwargs = {
        'dry_run': arguments['--dry-run'],
        'consider_old': arguments['--consider-old'],
        'grep': arguments['--grep']
    }

    lg = LawGit(arguments['<repopath>'], **kwargs)

    if arguments['autocommit']:
        lg.autocommit()


if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='LawGit 0.0.2')
    main(arguments)
