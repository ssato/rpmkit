#
# Copyright (C) 2016 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: MIT
#
# Requirements: gensim, nltk scikit-learn
#
"""
Design Doc:


- Text to analyze: Errata's description
- Methodologies:

  - Text Normalization:
  
    - Normalize to lower cases
    - Remove punctations,

"""
from __future__ import print_function

import datetime
import gensim
import gzip
import itertools
import logging
import nltk
import nltk.corpus
import operator
import optparse
import os.path
import sklearn.feature_extraction.text
import string
import sys
import tempfile

try:
    # First, try lxml which is compatible with elementtree and looks faster a
    # lot. See also: http://getpython3.com/diveintopython3/xml.html
    from lxml2 import etree as ET
except ImportError:
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        import elementtree.ElementTree as ET


_TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
_ES_FMT = "%(advisory)s,%(synopsis)s,%(issue_date)s"

_STEMMER = nltk.PorterStemmer()
stem = _STEMMER.stem

LOG = logging.getLogger(__name__)


def _setup_workdir(workdir=None):
    """
    :param workdir: Working directory to save results.
    :return: The path to workdir
    """
    if workdir is None:
        workdir = tempfile.mkdtemp(dir="/tmp", prefix="errata_for_releases-")
        LOG.info("Created: {}".format(workdir))
    else:
        if os.path.exists(workdir):
            assert os.path.isdir(workdir), "Not a dir: {}".format(workdir)
        else:
            os.makedirs(workdir)
            logging.info("Created: {}".format(workdir))

    return workdir


def tokenize(text, stopwords=None):
    """Tokenize given text.
    """
    if stopwords is None:
        stopwords = nltk.corpus.stopwords.words("english")

    return [stem(w) for w in nltk.wordpunct_tokenize(text)
            if w not in stopwords]


def analyze(errata):
    """
    :param errata: A list of dicts each represents basic errata info :: dict
    """
    cls = sklearn.feature_extraction.text.TfidfVectorizer
    vectorizer = cls(tokenizer=tokenize,
                     stop_words=nltk.corpus.stopwords.words("english"))

    edocs = {e["id"]: e["description"].translate(None, string.punctuation)
            for e in errata}

    tfidfs = vectorizer.fit_transform(edocs.values())
    fnames = vectorizer.get_feature_names()

    words = [sorted(itertools.izip_longest(fnames, tfidf.toarray()[0]),
                    key=operator.itemgetter(1), reverse=True)
             for tfidf in tfidfs]

    return (edocs, tfidfs, fnames, words)


# https://radimrehurek.com/gensim/tut1.html#corpus-formats
# https://radimrehurek.com/gensim/tut2.html
def make_corpus(docs, workdir):
    """
    :param docs: A list of docuemnts :: [str]
    """
    texts = [tokenize(doc) for doc in docs]  # :: [[str]]
    dic = gensim.corpora.Dictionary(texts)
    dic.save(os.path.join(workdir, "gensim.wordids"))

    corpus = [dic.doc2bow(text) for text in texts]
    gensim.corpora.MmCorpus.serialize(os.path.join(workdir, "gensim.mm"),
                                      corpus)
    return corpus


def make_models(workdir):
    """
    :param workdir: Working dir in which corpus, dict files are saved
    """
    corpus = gensim.corpora.MmCorpus(os.path.join(workdir, "gensim.mm"))
    dic = gensim.corpora.Dictionary.load(os.path.join(workdir, "gensim.wordids"))

    tfidf = gensim.models.TfidfModel(corpus)
    corpus_tfidf = tfidf[corpus]
    lsimod = gensim.models.lsimodel.LsiModel(corpus_tfidf, id2word=dic,
                                             num_topics=300)
    lsimod.save(os.path.join(workdir, "gensim.lsimodel"))
    LOG.info("LSI model: topics = %r", lsimod.show_topics())

    ldamod = gensim.models.ldamodel.LdaModel(corpus, id2word=dic, num_topics=100)
    ldamod.save(os.path.join(workdir, "gensim.ldamodel"))
    LOG.info("LDA model: topics = %r", ldamod.show_topics())

    return dict(lsi=lsimod, lda=ldamod)


def updi_xml_itr(updateinfo):
    """
    :param updateinfo: the content of updateinfo.xml :: str
    """
    root = ET.ElementTree(ET.fromstring(updateinfo)).getroot()
    for upd in root.findall("update"):
        uinfo = upd.attrib
        for k in "id title severity rights summary description".split():
            elem = upd.find(k)
            if elem is not None:
                uinfo[k] = elem.text

        for k in "issued updated".split():
            uinfo[k] = upd.find(k).attrib["date"]
        uinfo["refs"] = [r.attrib for r in upd.findall(".//reference")]
        uinfo["packages"] = [dict(filename=p.find("filename").text, **p.attrib)
                             for p in upd.findall(".//package")]
        yield uinfo


def get_errata_list_from_updateinfo_file(filepath):
    """
    Try to fetch the content of given repo metadata xml from remote.

    :param filepath: Path to updateinfo.xml.gz
    """
    uinfo = gzip.GzipFile(filename=filepath).read()
    return sorted(updi_xml_itr(uinfo), key=operator.itemgetter("issued"))


def option_parser():
    usage = """Usage: %prog [OPTION ...] UPDATEINFO_XML_GZ_PATH

    where UPDATEINFO_XML_GZ_PATH  Path to updateinfo.xml.gz
"""
    defaults = dict(workdir=None, verbose=False)

    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)
    p.add_option("-w", "--workdir", help="Working dir to save results")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    if options.verbose:
        LOG.setLevel(logging.DEBUG)

    if not args:
        p.print_help()
        sys.exit(1)

    aes = get_errata_list_from_updateinfo_by_repofile(distro["repoid"])

    if options.workdir:
        workdir = options.workdir
        if os.path.exists(workdir):
            assert os.path.isdir(workdir), "Not a dir: {}".format(workdir)
        else:
            os.makedirs(workdir)
            logging.info("Created: {}".format(workdir))
    else:
        workdir = tempfile.mkdtemp(dir="/tmp", prefix="errata_for_releases-")
        logging.info("Created: {}".format(workdir))

    output_results(errata, packages, updates, distro, workdir)


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
