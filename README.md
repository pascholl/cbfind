# cbfind
Index and search Cryptobib

# Requirements

Python 3 and the packages whoosh and pybtex, which can be installed by running in the terminal:

```pip install whoosh pybtex```

# Setup

On Linux or MacOS, download a copy of [Cryptobib](https://cryptobib.di.ens.fr/) into your home directory and run

```python3 cbfind.py -u```

from the location where you downloaded this repository. This will parse Cryptobib and generate a searchable database, which is then stored in the same directory as Cryptobib.

If Cryptobib is stored in a different directory, or you want the database stored elsewhere, you can use the options `-b` or `-d`. To show all options, run:

```python3 cbfind.py```

# Usage

Run `python3 cbfind.py <search query>`. By default, terms in the query are ANDed together, and the script searches in the title, author and year fields of the original bibtex entries. You can also search for acronyms like "KKW" or "Groth16", or specify "author:Groth year:2016" etc.

The results first display the bibtex citation key, together with the main details for the paper, including an ePrint URL if one was found.

