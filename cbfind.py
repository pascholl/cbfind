#!/usr/bin/env python3

"""
Simple script to index and search cryptobib

Requires whoosh and pybtex, which can be installed with:

$ pip3 install whoosh pybtex
"""

from whoosh import index
from whoosh.fields import Schema, TEXT, ID, NUMERIC, KEYWORD
from whoosh.qparser import MultifieldParser
from whoosh import highlight
import textwrap
import os
import sys
import re
from optparse import OptionParser

import logging
import logging.config

logger = logging.getLogger(__name__)

logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s %(funcName)s:%(lineno)d: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level':'DEBUG',
            'formatter': 'standard',
            'class':'logging.StreamHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'DEBUG',
            'formatter': 'standard',
            'propagate': True
        }
    }
})

# Get the value of the HOME environment variable
home_dir = os.environ['HOME']

# Use the HOME environment variable to construct the path to the file
INDEX_DIR_DEFAULT = os.path.join(home_dir, 'cryptobib', 'cbindex')
CRYPTOBIB_DEFAULT = os.path.join(home_dir, 'cryptobib', 'crypto.bib')
MAX_RESULTS_DEFAULT = 30

ABBREV_DEFAULT = 'abbrev3.bib'
BIBTEX_FIELDS = ['title', 'author', 'year', 'note']
SEARCHABLE_FIELDS = ['title', 'author', 'year', 'acronyms']

def get_schema():
    return Schema(
        ID=ID(stored=True),
        title=TEXT(stored=True),
        author=TEXT(stored=True),
        year=NUMERIC(stored=True, sortable=True),
        note=ID(stored=True),
        bibtex=TEXT(stored=True),
        acronyms=KEYWORD(stored=True, commas=True, lowercase=True)
    )

def create_index(cryptobib, indexdir):
    abbrevbib = os.path.join(os.path.dirname(cryptobib), ABBREV_DEFAULT)
    schema = get_schema()
    idx = index.create_in(indexdir, schema)
    logger.info(f'Parsing {cryptobib} and {abbrevbib}...')

    # Join the contents of abbrevbib and cryptobib into a temporary file
    with open(abbrevbib) as f1, open(cryptobib) as f2, open('tmp.bib', 'w') as f3:
        f3.write(f1.read() + '\n' + f2.read())

    from pybtex.database.input import bibtex
    from pybtex.database import BibliographyData
    cryptobib_db = bibtex.Parser().parse_file('tmp.bib')
    os.remove('tmp.bib')

    writer = idx.writer()
    eprint_urls = {}
    formatted_entries = {}
    logger.info('Generating search index...')
    for (ID, entry) in cryptobib_db.entries.items():
        formatted_entry = {'ID': entry.key}
        formatted_entry['bibtex'] = BibliographyData({ID: entry}).to_string('bibtex')

        authors = ''
        if 'author' in entry.persons:
            for person in entry.persons['author']:
                authors += ' '.join(person.first_names + person.middle_names + person.prelast_names + person.last_names) + ', '
        formatted_entry['author'] = str(authors[:-2])
        
        for key in BIBTEX_FIELDS:
            # remove '{}', replace '\n' with ' ' and convert to unicode
            # also strip out leading '\url' for note field
            if key in entry.fields:
                formatted_entry[key] = str(entry.fields[key]).translate({ord(c): v for (c,v) in
                        [('\n', str(' ')), ('{', None), ('}', None)]}).lstrip('\\url')
        formatted_entry['acronyms'] = ','.join(acronyms_from_ID(ID))
        formatted_entries[ID] = formatted_entry

        if ID.startswith('EPRINT') and 'title' in entry.fields:
            url = formatted_entry['note']
            eprint_urls[formatted_entry['title']] = (url, ID)

    for (ID,entry) in formatted_entries.items():
        # Copy note from eprint to published version, and remove eprint entry from search index
        # TODO: earlier duplicates are not removed
        if not ID.startswith('EPRINT') and 'title' in entry:
            if entry['title'] in eprint_urls:
                entry['note'] = eprint_urls[entry['title']][0]
                # todo: figure out how to remove eprint entry
                eprint_ID = eprint_urls[entry['title']][1]
                formatted_entries[eprint_ID]['ignore'] = True
        if 'ignore' not in entry:
            writer.add_document(**entry)
    writer.commit()
    return idx

def acronyms_from_ID(id):
    """
    Returns e.g. ['GHS', 'GHS12'] from 'C:GenHalSma12', or ['Groth16'] from 'C:Groth16'
    """
    # extract initials from part after ":"
    id = id.split(':')[-1]
    year = re.search(r'\d+[abcdefgh]?$', id)
    if year is None:
        # probably a weird entry with no acronym
        return []
    else:
        year = year.group()
    initials = ''.join(c for c in id if c.isupper())
    # 
    if len(initials) > 2:
        return [initials, initials + year]
    elif len(initials) == 2:
        return [initials + year]
    else:
        return [id]

class MyFormatter(highlight.Formatter):
    def format_token(self, text, token, replace=False):
        ttext = highlight.get_text(text, token, replace)
        return "|<%s|" % ttext

def highlight_str(string, color=False, bold=False):
    if sys.stdout.isatty():
        attr = []
        if color:
            # green
            attr.append('32')
        if bold:
            attr.append('1')
        return '\x1b[%sm%s\x1b[0m' % (';'.join(attr), string)
    else:
        return string

def search_index(idx, query, searchlimit=10, outputbibtex=False):
    mp = MultifieldParser(SEARCHABLE_FIELDS, schema=idx.schema)
    q = mp.parse(query)
    with idx.searcher() as searcher:
        results = searcher.search(q, limit=searchlimit, sortedby='year', reverse=True)
        print(f'Showing up to {searchlimit} results for query \"{query}\":\n(use -l 50 for more)')
        results.fragmenter = highlight.WholeFragmenter()
        results.formatter = MyFormatter()
        indent = ' '*8
        preferredWidth = 80
        wrapper = textwrap.TextWrapper(initial_indent=indent, width=preferredWidth,
            subsequent_indent=indent)

        all_output = []
        for hit in results:
            all_output.append(highlight_str('\n' + hit['ID'], bold=True))
            for field in hit.fields():
                if field == 'ID' or field == 'bibtex':
                    continue
                tokens = hit.highlights(field, minscore=0).split('|')
                output = ''
                for token in tokens:
                    if token.startswith('<'):
                        output += highlight_str(token[1:], color=True)
                    else:
                        output += token
                if field != next(reversed(hit.fields().keys())):
                    output += ','
                #logging.info(output)
                #print(output)
                all_output.append(wrapper.fill(output))
            if outputbibtex:
                all_output.append(hit['bibtex'])
        #print("\n".join(all_output))
        import pydoc
        pydoc.pipepager('\n'.join(all_output), cmd='less -RX')

def main():
    usage = "usage: cbfind [options] <query>\n\nQuery supports OR/AND " + \
        "and field-specific keywords such as \"author:<keyword>\", \"title:<keyword>\""
    parser = OptionParser(usage=usage)
    parser.add_option("-b",
                    dest="cryptobib", default=CRYPTOBIB_DEFAULT,
                    help=f"Bibtex file to index (default: {CRYPTOBIB_DEFAULT})")
    parser.add_option("-d",
                    dest="indexdir", default=INDEX_DIR_DEFAULT,
                    help=f"Directory where index is stored (default: {INDEX_DIR_DEFAULT})")
    parser.add_option("-u",
                    dest="update", action="store_true", default=False,
                    help="Re-generate the search index from Cryptobib")
    parser.add_option("-t",
                    dest="bibtex", action="store_true", default=False,
                    help="Output raw bibtex in search results")
    parser.add_option("-l",
                    dest="limit", default=MAX_RESULTS_DEFAULT,
                    help=f"Limit for number of search results (default: {MAX_RESULTS_DEFAULT})")

    options,args = parser.parse_args()
    if len(args) < 1 and not options.update:
        parser.print_help()
        return

    if not os.path.exists(options.indexdir) or options.update:
        if not os.path.exists(options.indexdir):
            os.mkdir(options.indexdir)
        idx = create_index(options.cryptobib, options.indexdir)
    else:
        idx = index.open_dir(options.indexdir)
    query = ' '.join(args)
    if len(args) >= 1:
        search_index(idx, query, searchlimit=int(options.limit), outputbibtex=options.bibtex)

if __name__ == '__main__':
    main()
