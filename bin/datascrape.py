#!/usr/bin/env python
import os
LIBDIR = os.path.join(os.environ["SPLUNK_HOME"], 'etc', 'apps', 'TA-data_scrape', 'bin', 'lib')
import sys
if LIBDIR not in sys.path:
    sys.path.append(LIBDIR)

import urllib2
import urlparse
from time import sleep, time
from bs4 import BeautifulSoup
import re
import glob
import logging, logging.handlers
#from splunk_http_event_collector import http_event_collector

# sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators


@Configuration(local=True)
class ScrapeCommand(GeneratingCommand):
    """ Scrape given url, capturing text between capture_after and break_before.



    ##Syntax

    %(syntax)

    ##Description

    %(description)

    """

    logger = logging.getLogger('splunk.Scrape')
    SPLUNK_HOME = os.environ['SPLUNK_HOME']

    LOGGING_DEFAULT_CONFIG_FILE = os.path.join(SPLUNK_HOME, 'etc', 'log.cfg')
    LOGGING_LOCAL_CONFIG_FILE = os.path.join(SPLUNK_HOME, 'etc', 'log-local.cfg')
    LOGGING_STANZA_NAME = 'python'
    LOGGING_FILE_NAME = "Scrape.log"
    BASE_LOG_PATH = os.path.join('var', 'log', 'splunk')
    LOGGING_FORMAT = "%(asctime)s %(levelname)-s\t%(module)s:%(lineno)d - %(message)s"
    splunk_log_handler = logging.handlers.RotatingFileHandler(
        os.path.join(SPLUNK_HOME, BASE_LOG_PATH, LOGGING_FILE_NAME), mode='a')
    splunk_log_handler.setFormatter(logging.Formatter(LOGGING_FORMAT))
    logger.addHandler(splunk_log_handler)
    logger.setLevel(logging.INFO)

    url = Option()
    mask = Option()
    capture_after = Option()
    break_before = Option()
    single_event_mode = Option(validate=validators.Boolean())
    crawl = Option(validate=validators.Boolean())
    sourcetype = Option()
    hec_token = Option()
    download_files = Option(validate=validators.Boolean())
    download_only = Option(validate=validators.Boolean())
    path_name = Option()
    hec_host = Option()
    index = Option()
    log_level = Option()
    skip_download = Option(validate=validators.Boolean())

    def normalize_input(self, config):
        '''

        change string values to boolean where appropriate
        :param config:
        :param self:
        :return:
        '''

        boolean_config_options = ['crawl', 'single_event_mode', 'download_files', 'download_only', 'skip_download']
        true_values = ["true", "t"]
        false_values = ["false", "f"]

        for item in config.keys():
            if item in boolean_config_options and isinstance(config[item], str):
                if config[item].lower() in true_values:
                    config[item] = True
                elif config[item].lower() in false_values:
                    config[item] = False

        if config['mask']:
            if ',' in config['mask']:
                self.logger.debug("splitting mask which is right now " + config['mask'])
                config['mask'] = config['mask'].split(',')

        return config

    def generate(self):
        url = self.url
        mask = self.mask
        capture_after = self.capture_after
        break_before = self.break_before
        single_event_mode = self.single_event_mode
        crawl = self.crawl
        sourcetype = self.sourcetype
        hec_token = self.hec_token
        hec_host = self.hec_host
        download_files = self.download_files
        download_only = self.download_only
        path_name = self.path_name
        index = self.index
        log_level = self.log_level
        skip_download = self.skip_download

        self.logger.debug("starting command")
        if skip_download is None:
            skip_download = False

        if log_level:
            if log_level.lower() == "debug":
                self.logger.setLevel(logging.DEBUG)
            else:
                self.logger.setLevel(logging.INFO)

        config = {'url': url, 'mask': mask, 'capture_after': capture_after, 'break_before': break_before,
                  'single_event_mode': single_event_mode, 'crawl': crawl,
                  'download_only': download_only, 'skip_download': skip_download}
        config = self.normalize_input(config)

        if hec_token:
            self.logger.debug("found hec token parameter")
            hec_endpoint = None
            #if not hec_host:
            #    hec_host = "localhost"
            #hec_endpoint = http_event_collector(hec_token, hec_host)
            #self.logger.info("created hec endpoint")
        else:
            hec_endpoint = None
        event_options = {'sourcetype': sourcetype, 'index': index}

        if not path_name:
            download_path = os.path.join(os.path.dirname(LIBDIR), 'downloads')
        else:
            download_path = os.path.join(os.path.dirname(LIBDIR), 'downloads', 'path_name')

        config['path'] = download_path
        self.logger.debug("scraping with options: " + str(config))

        if not skip_download:
            if not os.path.exists(download_path):
                os.mkdir(download_path)

            if download_files:
                self.find_all_downloads(config)

        files = self.get_file_list(download_path)
        files_processed_count = 0
        self.logger.debug("we have downloaded " + str(len(files)) + " files")

        if not download_only:
            for file_name in files:
                #self.logger.info("parsing event for " + file_name)
                events = self.parse_events(file_name, config)
                #self.logger.info("formatting output for event")
                output = self.format_output(events)
                if output:

                    if hec_endpoint:
                        self.send_http_event(hec_endpoint, event_options)
                    else:
                        if sourcetype:
                            yield {'_time': time(), '_raw': output, 'sourcetype': sourcetype}
                        else:
                            yield {'_time': time(), '_raw': output}

                    files_processed_count = files_processed_count + 1
        else:
            for fn in files:
                yield {'_time': time(), '_raw': 'downloaded ' + '/' + config['path'] + fn}

        #self.finish()

    def find_all_downloads(self, config):
        """
            Starting with config['url'] and crawl any additional pages until we reach a target.
            Target pages have no embedded links
        :param config:
        :param logger:
        :param self:
        :return:
        """
        url = config['url']
        mask = config['mask']
        links = None

        self.logger.debug("find_all_downloads begin with:" + str(url))
        links = self.get_page_links(url, mask)
        if not links:
            # no links found on page, we must have found a download target
            parsed_url = urlparse.urlparse(url)
            self.download_file(config['path'], url, mask, config['download_only'])
            sleep(0.2)

        while links:

            url = links.pop()
            # self.logger.debug(" looking at page: " + url)
            mask = self.get_url_mask(url, config)
            if mask is None:
                # self.logger.debug("mask is none, skip url " + url)
                continue
            new_links = self.get_page_links(url, "")

            if not new_links:
                self.download_file(config['path'], url, mask, config['download_only'])
                sleep(0.2)
            else:
                # self.logger.debug(" page " + url + " had links " + str(new_links))
                for item in new_links:
                    links.append(item)

    def download_file(self, download_path, url, mask, download_only):
        """

        :param download_path:
        :param url:
        :param mask:
        :param download_only:
        :param logger:
        :param self:
        :return:
        """

        self.logger.debug("trying to download " + str(url) + " with options: " + str(download_path) + "," + str(mask) +
                          ":" + str(download_only))
        filename = ''
        try:
            filename = download_path + '/' + url.split(mask)[1][0:].replace('/', '_')
        except ValueError:
            print("failed to generate filename for {0}, {1}".format(url, mask))
        try:
            url_item = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print(str(e.errno) + " HTTP ERROR RETURNED FROM URL " + str(url))
            sys.exit(1)
        except urllib2.URLError as e:
            print(e.reason + ": url was " + str(url))
            sys.exit(1)
        data = url_item.read()
        with open(filename, 'w') as file_handle:
            file_handle.write(data)

    @staticmethod
    def read_url(url, mask):
        """

        :param url:
        :param mask:
        :return:
        """
        try:
            url_handle = urllib2.urlopen(url)
        except urllib2.HTTPError as error:
            print("url read failed for {0}: {1} {2}".format(url, error.code, error.reason))
        except urllib2.URLError as error:
            print("url read failed for {0}: {1}".format(url, error.reason))
        data = url_handle.read()

        return data

    def get_page_links(self, url, href_mask):
        """

        :param url:
        :param href_mask:
        :return:
        """

        if url.rfind('.') > url.rfind('/'):  # url ends with . + file type; is not a web directory name
            page_type = url[url.rfind('.')+1:]

            if page_type.lower() == 'pdf' or page_type.lower() == 'csv' or page_type == 'txt':
                return None

        try:
            html_document = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print(str(e.errno) + " HTTP ERROR RETURNED FROM URL " + str(url))
            sys.exit(1)
        except urllib2.URLError as e:
            print(e.reason + ": url was " + str(url))
            sys.exit(1)

        soup = BeautifulSoup(html_document.read(), 'html.parser')
        links = []
        formatted_links = []

        for link in soup.find_all('a'):
            links.append(link.get('href'))
        if not links:
            return None
        u = urlparse.urlparse(url)

        # find correct mask
        # self.logger.debug("found these links:" + str(links))
        links = self.filter_links(links)

        for item in links:
            if item[0] == '/':  # href is relative!
                formatted_links.append(u.scheme + "://" + u.netloc + item)
            else:
                formatted_links.append(item)
        return formatted_links

    @staticmethod
    def filter_links(links):
        """
        :param links: list of strings representing urls
        :return:
        """

        filtered_links = []
        if not links:
            return None
        for item in links:
            if item:
                if '/Elections/Resources/Files/htm' in item or '/Elections/Results' in item:
                    filtered_links.append(item)

        return filtered_links

    @staticmethod
    def get_url_mask(url, config):
        """
        Get the part of the url that is most significant, mainly used for building filename of output
        :param url:
        :param config:
        :return:
        """

        if not url:
            return None

        if isinstance(config['mask'], list):
            for item in config['mask']:
                if item in url:
                    return item
        elif isinstance(config['mask'], str):
            if config['mask'] in url:
                return config['mask']

    @staticmethod
    def get_file_list(path):
        """

        :param path:
        :return:
        """
        files = os.listdir(path)
        full_path = []
        for item in files:
            full_path.append(path + '/' + item)
        return full_path

    @staticmethod
    def parse_events(file_name, config):
        """

        :param file:
        :param config:
        :return:
        """
        #TODO cant assume breaks are only meaningful text on line...
        # capture text on same line but after start_before and before break_after string!!

        output = ''
        print("parsing " + str(file))

        with open(file_name, 'r') as fh:
            line = fh.readline()
            while config['capture_after'] not in line:
                if len(line) == 0:
                    output = None
                    print(str(file) + " did not find event break begin " + config['capture_after'])
                line = fh.readline()

            line = fh.readline()
            while config['break_before'] not in line:
                if len(line) == 0:
                    output = None
                    print(str(file) + " did not find event break end " + config['break_before'])
                    break
                output = output + line
                line = fh.readline()

        return output

    @staticmethod
    def format_output(blob):
        """
        Convert 2+ whitespace to ;
        :param blob:
        :return:
        """
        if blob is None:
            return
        blob = re.sub(r'\n', ';', blob)
        blob = re.sub(r'\s*\.  +', ';', blob).strip()
        blob = re.sub(r'\s{2,}', ';', blob).strip()
        blob = re.sub(r'\s\.;', ';', blob).strip()
        blob = re.sub(r'\.;', ';', blob).strip()
        blob = re.sub(r';{2,}', ';', blob).strip()

        return blob

    def send_http_event(self, hec_endpoint, blob, **kwargs):
        """

        :param hec_endpoint:
        :param blob:
        :return:
        """
        if blob is None:
            return

        payload = {}

        for item in kwargs.keys():
            if kwargs[item]:
                payload.update({item: kwargs[item]})

        payload.update({"event": blob})
        hec_endpoint.sendEvent(payload)
        hec_endpoint.flushBatch()


dispatch(ScrapeCommand, sys.argv, sys.stdin, sys.stdout, __name__)
