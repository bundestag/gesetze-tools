# -*- encoding: utf-8 -*-
"""LawGit - Semi-automatic law change commits.

Usage:
  lawgit.py autocommit <repopath> [--dry-run] [--consider-old]
  lawgit.py -h | --help
  lawgit.py --version

Options:
  --dry-run         Make a dry run.
  --consider-old    Consider old laws for commits.
  -h --help         Show this screen.
  --version         Show version.

"""
import re
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict

from git import Repo
from git.exc import GitCommandError


class TransientState(Exception):
    pass


class BGBlSource(object):
    """BGBl as a source for law change"""

    change_re = [
        re.compile(u'BGBl +(?P<part>I+):? *(?P<year>\d{4}), +(?:S\. )?(?P<page>\d+)'),
        re.compile('\d{1,2}\.\.?\d{1,2}\.\.?(?P<year>\d{4}) (?P<part>I+) (?:S\. )?(?P<page>\d+)'),
        re.compile(u'(?P<year>\d{4}).{,8}?BGBl\.? +(?P<part>I+):? +(?:S\. )?(?P<page>\d+)')
    ]

    def __init__(self, source):
        self.load(source)

    def load(self, source):
        self.data = {}
        data = json.load(file(source))
        for key, toc_list in data.iteritems():
            for toc in toc_list:
                if toc['kind'] == 'meta':
                    continue
                toc['part_i'] = 'I' * toc['part']
                self.data[(toc['year'], toc['page'], toc['part'])] = toc

    def find_candidates(self, lines):
        candidates = []
        for line in lines:
            for c_re in self.change_re:
                for match in c_re.finditer(line):
                    if u"noch nicht berücksichtigt" in line:
                        raise TransientState
                    key = (
                        int(match.group('year')),
                        int(match.group('page')),
                        len(match.group('part'))
                    )
                    if key in self.data:
                        candidates.append(key)
        return candidates

    def get_order_key(self, key):
        return self.get_date(key)

    def get_date(self, key):
        bgbl_entry = self.data[key]
        return datetime.strptime(bgbl_entry['date'], '%d.%m.%Y')

    def get_branch_name(self, key):
        bgbl_entry = self.data[key]
        return 'bgbl/%s/%s-%s' % (
            bgbl_entry['year'],
            bgbl_entry['part'],
            bgbl_entry['number']
        )

    def get_ident(self, key):
        bgbl_entry = self.data[key]
        return bgbl_entry['href']

    def get_message(self, key):
        bgbl_entry = self.data[key]
        return ('%(name)s\n\n%(date)s: BGBl %(part_i)s: %(year)s, '
                '%(page)s (Nr. %(number)s)' % bgbl_entry)


class BAnzSource(object):
    """BAnz as a source for law change"""

    def __init__(self, source):
        self.load(source)

    def load(self, source):
        self.data = json.load(file(source))

    def find_candidates(self, lines):
        candidates = []
        for line in lines:
            line = re.sub('[^\w \.]', '', line)
            line = re.sub(' \d{4}, ', ' ', line)
            for key in self.data:
                if key in line:
                    if u"noch nicht berücksichtigt" in line:
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
        return 'banz/%s/%s' % (
            entry['date'].split('.')[2],
            '-'.join(reversed(entry['date'].split('.')[:2]))
        )

    def get_ident(self, key):
        return key

    def get_message(self, key):
        entry = dict(self.data[key])
        additional_str = ', '.join(entry['additional'])
        if additional_str:
            entry['additional_str'] = ', %s' % additional_str
        else:
            entry['additional_str'] = ''
        return ('%(name)s\n\n%(date)s: %(ident)s, %(public_body)s'
                '%(additional_str)s' % entry)


class LawGit(object):
    laws = defaultdict(list)
    law_changes = {}
    bgbl_changes = defaultdict(list)

    def __init__(self, path, dry_run=False, consider_old=False):
        self.path = path
        self.dry_run = dry_run
        self.consider_old = consider_old
        self.repo = Repo(path)
        self.sources = [
            BGBlSource('data/bgbl.json'),
            BAnzSource('data/banz.json')
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
                print "Skipped %s %s (too old)" % (law, result)
                continue
            branch_name = source.get_branch_name(key)
            ident = source.get_ident(key)
            branches[branch_name].setdefault(ident, [])
            branches[branch_name][ident].append((law, source, key))
        return branches

    def collect_laws(self):
        hcommit = self.repo.head.commit
        wdiff = hcommit.diff(None, create_patch=True)
        for diff in wdiff:
            law_name = diff.b_blob.path.split('/')[1]
            self.laws[law_name].append(diff.b_blob.path)
            filename = '/'.join(diff.b_blob.path.split('/')[:2] + ['index.md'])
            filename = os.path.join(self.path, filename)
            self.law_changes[law_name] = (False, diff.diff, filename)

        for filename in self.repo.untracked_files:
            law_name = filename.split('/')[1]
            self.laws[law_name].append(filename)
            filename = '/'.join(filename.split('/')[:2] + ['index.md'])
            filename = os.path.join(self.path, filename)
            with file(filename) as f:
                self.law_changes[law_name] = (True, f.read(), filename)

    def determine_source(self, law_name):
        new_file, lines, filename = self.law_changes[law_name]
        lines = [line.decode('utf-8') for line in lines.splitlines()]
        candidates = []
        for source in self.sources:
            try:
                candidates.extend([(source, c) for c in source.find_candidates(lines)])
            except TransientState:
                return None
        if not candidates:
            with file(filename) as f:
                lines = [line.decode('utf-8') for line in f.read().splitlines()]
            for source in self.sources:
                try:
                    candidates.extend([(source, c) for c in source.find_candidates(lines)])
                except TransientState:
                    return None
            if not candidates:
                return None
        return sorted(candidates, key=lambda x: x[0].get_order_key(x[1]))[-1]

    def autocommit(self):
        branches = self.prepare_commits()
        for branch in sorted(branches.keys()):
            self.commit_branch(branch, branches[branch])

    def commit_branch(self, branch, commits):
        if not self.dry_run:
            self.repo.git.stash()
        try:
            print "git checkout -b %s" % branch
            if not self.dry_run:
                self.repo.git.checkout(b=branch)
        except GitCommandError:
            print "git checkout %s" % branch
            if not self.dry_run:
                self.repo.git.checkout(branch)
        if not self.dry_run:
            self.repo.git.merge('master')
            self.repo.git.stash('pop')
        for ident in commits:
            for law_name, source, key in commits[ident]:
                for filename in self.laws[law_name]:
                    if os.path.exists(os.path.join(self.path, filename)):
                        print "git add %s" % filename
                        if not self.dry_run:
                            self.repo.index.add([filename])
                    else:
                        print "git rm %s" % filename
                        if not self.dry_run:
                            self.repo.index.remove([filename])
            msg = source.get_message(key)
            print 'git commit -m"%s"' % msg
            if not self.dry_run:
                self.repo.index.commit(msg.encode('utf-8'))
            print ""
        print "git checkout master"
        if not self.dry_run:
            self.repo.heads.master.checkout()
        print "git merge %s --no-ff" % branch
        if not self.dry_run:
            self.repo.git.merge(branch, no_ff=True)


def main(arguments):
    kwargs = {
        'dry_run': arguments['--dry-run'],
        'consider_old': arguments['--consider-old']
    }

    lg = LawGit(arguments['<repopath>'], **kwargs)

    if arguments['autocommit']:
        lg.autocommit()

if __name__ == '__main__':
    from docopt import docopt
    arguments = docopt(__doc__, version='LawGit 0.0.2')
    main(arguments)
