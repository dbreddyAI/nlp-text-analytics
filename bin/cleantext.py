#!/opt/splunk/bin/python

import sys
import re
import os
import logging, logging.handlers

from string import punctuation, digits, maketrans

from splunk.appserver.mrsparkle.lib.util import make_splunkhome_path
from splunk import setupSplunkLogger
from nltk import word_tokenize, pos_tag
from nltk.data import path as nltk_data_path
from nltk.corpus import wordnet, stopwords as stop_words
from nltk.stem import WordNetLemmatizer, PorterStemmer
from splunklib import six
from splunklib.searchcommands import dispatch, StreamingCommand, Configuration, Option, validators

BASE_DIR = make_splunkhome_path(["etc","apps","nlp-text-analytics"])
CORPORA_DIR = os.path.join(BASE_DIR,'bin','nltk_data')
nltk_data_path.append(CORPORA_DIR)


@Configuration()
class CleanText(StreamingCommand):
    """ Counts the number of non-overlapping matches to a regular expression in a set of fields.

    ##Syntax

    .. code-block::
        cleantext lowercase=<boolean> pattern=<regular_expression> <field-list>

    ##Description

    A count of the number of non-overlapping matches to the regular expression specified by `pattern` is computed for
    each record processed. The result is stored in the field specified by `fieldname`. If `fieldname` exists, its value
    is replaced. If `fieldname` does not exist, it is created. Event records are otherwise passed through to the next
    pipeline processor unmodified.

    ##Example

    Count the number of words in the `text` of each tweet in tweets.csv and store the result in `word_count`.

    .. code-block::
        | inputlookup tweets | countmatches fieldname=word_count pattern="\\w+" text
    """

    textfield = Option(
        require=True,
        doc='''
        **Syntax:** **textfield=***<fieldname>*
        **Description:** Name of the field that will contain the text to search against''',
        validate=validators.Fieldname())
    default_clean = Option(
        default=True,
        doc='''**Syntax:** **lowercase=***<boolean>*
        **Description:** Change text to lowercase, remove punctuation, and removed numbers, defaults to true''',
        validate=validators.Boolean()
        ) 	
    remove_urls = Option(
        default=True,
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Remove html links as part of text cleaning, defaults to true''',
        validate=validators.Boolean()
        ) 	
    remove_stopwords = Option(
        default=True,
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Remove stopwords as part of text cleaning, defaults to true''',
        validate=validators.Boolean()
        ) 	
    base_word = Option(
        default=True,
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Convert words to a base form as part of text cleaning, defaults to true and subject to value of base_type setting''',
        validate=validators.Boolean()
        ) 	
    base_type = Option(
        default='lemma',
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Options are lemma, lemma_pos, or stem, defaults to lemma and subject to value of base_word setting being true''',
        ) 	
    mv = Option(
        default=True,
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Returns words as multivalue otherwise words are space seperated, defaults to true''',
        validate=validators.Boolean()
        ) 	
    force_nltk_tokenize = Option(
        default=False,
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Forces use of better NLTK word tokenizer but is slower, defaults to false''',
        validate=validators.Boolean()
        ) 	
    pos_tagset = Option(
        default=None,
        doc='''**Syntax:** **remove_punct=***<boolean>*
        **Description:** Options are universal, wsj, or brown; defaults to universal and subject to base_type set to "lemma_pos"''',
        ) 	

    #http://dev.splunk.com/view/logging/SP-CAAAFCN
    def setup_logging(self):
        logger = logging.getLogger('splunk.foo')    
        SPLUNK_HOME = os.environ['SPLUNK_HOME']
        
        LOGGING_DEFAULT_CONFIG_FILE = os.path.join(SPLUNK_HOME, 'etc', 'log.cfg')
        LOGGING_LOCAL_CONFIG_FILE = os.path.join(SPLUNK_HOME, 'etc', 'log-local.cfg')
        LOGGING_STANZA_NAME = 'python'
        LOGGING_FILE_NAME = "nlp-text-analytics.log"
        BASE_LOG_PATH = os.path.join('var', 'log', 'splunk')
        LOGGING_FORMAT = "%(asctime)s %(levelname)-s\t%(module)s:%(lineno)d - %(message)s"
        splunk_log_handler = logging.handlers.RotatingFileHandler(
            os.path.join(
                SPLUNK_HOME,
                BASE_LOG_PATH,
                LOGGING_FILE_NAME
            ), mode='a') 
        splunk_log_handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
        logger.addHandler(splunk_log_handler)
        setupSplunkLogger(
            logger,
            LOGGING_DEFAULT_CONFIG_FILE,
            LOGGING_LOCAL_CONFIG_FILE,
            LOGGING_STANZA_NAME
        )
        return logger

    #https://stackoverflow.com/a/15590384
    def get_wordnet_pos(self, treebank_tag):
        if treebank_tag.startswith('J'):
            return wordnet.ADJ
        elif treebank_tag.startswith('V'):
            return wordnet.VERB
        elif treebank_tag.startswith('N'):
            return wordnet.NOUN
        elif treebank_tag.startswith('R'):
            return wordnet.ADV
        else:
            return 'n'
    
    def f_remove_urls(self, text):
        return re.sub(
            'https?://[^\b\s<]+',
            '',
            text
        )

    def stream(self, records):
        logger = self.setup_logging()
        logger.info('textfield set to: ' + self.textfield)
        for record in records:
            #URL removal
            if self.remove_urls:
                record[self.textfield] = self.f_remove_urls(
                    record[self.textfield]
                )
            #Tokenization
            if (self.base_word and self.base_type == 'lemma_pos') or self.force_nltk_tokenize:
                #lemma_pos - if option is lemmatization with POS tagging do cleaning and stopword options now
                if (self.base_word and self.base_type == 'lemma_pos'):
                    record['pos_tuple'] = pos_tag(
                        word_tokenize(
                            six.text_type(record[self.textfield].decode("utf-8"))
                        ),
                        tagset=self.pos_tagset
                    )
                    if self.default_clean and self.remove_stopwords:
                        stopwords = set(stop_words.words('english'))
                        record['pos_tuple'] = [
                            [
                            re.sub(r'[\W\d]','',text[0]).lower(),
                            text[1]
                            ]
                            for text in
                            record['pos_tuple']
                            if re.sub(r'[\W\d]','',text[0]).lower() not in stopwords
                            and not re.search(r'[\W]',text[0])
                        ]
                    elif self.default_clean and not self.remove_stopwords:
                        record['pos_tuple'] = [
                            [
                            re.sub(r'[\W\d]','',text[0]).lower(),
                            text[1]
                            ]
                            for text in
                            record['pos_tuple']
                            if not re.search(r'[\W]',text[0])
                        ]
                elif self.force_nltk_tokenize:
                    record[self.textfield] = word_tokenize(
                        record[self.textfield]
                    )
            elif self.default_clean or (self.base_word and self.base_type == 'lemma'):
                #https://stackoverflow.com/a/1059601
                record[self.textfield] = re.split('\W+', record[self.textfield])
            else:
                record[self.textfield] = record[self.textfield].split()
            #Default Clean
            if self.default_clean and not self.base_type == 'lemma_pos':
                record[self.textfield] = [
                    re.sub(r'[\W\d]','',text).lower()
                    for text in
                    record[self.textfield]
                ]
            #Lemmatization with POS tagging
            if self.base_word and self.base_type == 'lemma_pos':
                    lm = WordNetLemmatizer()
                    tuple_list = []
                    tag_list = []
                    record[self.textfield] = []
                    record['pos_tag'] = []
                    for text in record['pos_tuple']:
                        keep_text = lm.lemmatize(
                                text[0],
                                self.get_wordnet_pos(text[1])
                            )
                        if keep_text:
                            record[self.textfield].append(keep_text)
                            tuple_list.append((keep_text,text[1]))
                            tag_list.append(text[1])
                            record['pos_tag'] = tag_list
                            record['pos_tuple'] = tuple_list
            #Lemmatization or Stemming with stopword removal
            if self.remove_stopwords and self.base_word and self.base_type != 'lemma_pos':
                stopwords = set(stop_words.words('english'))
                if self.base_type == 'lemma':
                    lm = WordNetLemmatizer()
                    record[self.textfield] = [
                        lm.lemmatize(text)
                        for text in
                        record[self.textfield]
                        if text not in stopwords
                    ]
                if self.base_type == 'stem':
                    ps = PorterStemmer()
                    record[self.textfield] = [
                        ps.stem(text)
                        for text in
                        record[self.textfield]
                        if text not in stopwords
                    ]
            #Lemmatization or Stemming without stopword removal
            if not self.remove_stopwords and self.base_word:
                if self.base_type == 'lemma':
                    lm = WordNetLemmatizer()
                    record[self.textfield] = [
                        lm.lemmatize(text)
                        for text in
                        record[self.textfield]
                    ]
                if self.base_type == 'stem':
                    ps = PorterStemmer()
                    record[self.textfield] = [
                        ps.stem(text)
                        for text in
                        record[self.textfield]
                    ]
            #Stopword Removal
            if self.remove_stopwords and not self.base_word:
                stopwords = set(stop_words.words('english'))
                record[self.textfield] = [
                    text 
                    for text in
                    record[self.textfield]
                    if text not in stopwords
                    ]
            #Final Multi-Value Output
            if not self.mv:
                record[self.textfield] = ' '.join(record[self.textfield])
                try:
                    record['pos_tag'] = ' '.join(record['pos_tag'])
                except:
                    pass

            yield record

dispatch(CleanText, sys.argv, sys.stdin, sys.stdout, __name__)
