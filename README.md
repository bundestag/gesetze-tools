BundesGit Gesetze Tools
=======================

These scripts are used to keep the law repository up to date.

Install requirements:

    pip install -r requirements.txt


For help see their docstring, command line help or source code.

## lawde.py

Downloads all laws as XML files from
[www.gesetze-im-internet.de](http://www.gesetze-im-internet.de/)
and extracts them to a directory.


## lawdown.py

Converts all XML laws to Markdown and copies them with other files related
to the law into specified working directory.


## bgbl_scraper.py

Scrapes the table of contents of all issues of the Bundesgesetzblatt and dumps
the result to JSON.


## banz_scraper.py

Scrapes the table of contents of all available issues of the Bundesanzeiger and
dumps the result to JSON.


## lawgit.py

Checks the repositories working directory for changes, tries to find relations
to table of content entries in BGBl and BAnz data, commits the changes to a branch
and merges the branch into master.