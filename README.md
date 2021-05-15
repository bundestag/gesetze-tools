# BundesGit Gesetze Tools

These scripts are used to keep the [law repository](https://github.com/bundestag/gesetze) up to date.

Install requirements:
```bash
pip install -r requirements.txt
```

For help, see the docstring of the scripts, command line help or source code.


## Download laws (`lawde.py`)

Downloads all laws as XML files from
[www.gesetze-im-internet.de](http://www.gesetze-im-internet.de/)
and extracts them to a directory.

### Usage

Update your list of laws first:
```bash
python3 lawde.py updatelist
```

You can then download all laws by calling
```bash
python3 lawde.py loadall
```
Which will take approx. 2-3hrs.

Alternatively, you can find the individual law you're interested in in [./data/laws.json](./data/laws.json), which is mostly a list of laws in this form:
```bash
{"slug": "<shortname>", "name": "<longname>", "abbreviation": "<abbreviation>"}
```
You can download individual laws by calling
```bash
python3 lawde.py load <shortname>
```

Last tested: 2021-05-15 SUCCESS


## Convert to Markdown (`lawdown.py`)

Converts all downloaded XML laws to Markdown format and copies them with other files related
to the law into specified working directory.

### Usage

```bash
python3 lawdown.py convert <inpath> <outpath>
python3 lawdown.py convert ./laws ./laws-md
```

Last tested: 2021-05-15 SUCCESS


## Scaper Bundesgesetzblatt (`bgbl_scraper.py`)

Scrapes the table of contents of all issues of the Bundesgesetzblatt and dumps
the result to JSON.

```bash
python3 bgbl_scraper.py data/bgbl.json
```

Last tested: 2021-05-15 SUCCESS


## Scaper Bundesanzeiger (`banz_scraper.py`)

Scrapes the table of contents of all available issues of the Bundesanzeiger and
dumps the result to JSON.

Last tested: 2020-12-23 SUCCESS


## Scaper Verkehrsblatt (`vkbl_scraper.py`)

Scrapes the table of contents of all available issues of the Verkehrsblatt and
dumps the result to JSON.

```bash
python3 vkbl_scraper.py data/vkbl.json
```

Last tested: 2021-05-15 SUCCESS


## Commit changes (`lawgit.py`)

Checks the repositories working directory for changes, tries to find relations
to table of content entries in BGBl and BAnz data, commits the changes to a branch
and merges the branch into master.

Last tested: 2017-01-14 SUCCESS
