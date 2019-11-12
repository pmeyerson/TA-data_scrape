#!/usr/bin/env python
import os
LIBDIR = os.path.join(os.environ["SPLUNK_HOME"], 'etc', 'apps', 'TA-data_scrape', 'bin', 'lib')
#LIBDIR = os.path.join(os.getcwd(), 'lib')
import sys
if LIBDIR not in sys.path:
    sys.path.append(LIBDIR)

try:
    import urllib2
    import urlparse
    from time import sleep, time
    from bs4 import BeautifulSoup
    import re
    import glob
    import logging, logging.handlers
except Exception:
    print("Unable to import modules.  Check environment variable SPLUNK_HOME is set correctly")
    sys.exit(1)


#sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators


@Configuration(type='events', retainsevents=True, streaming=False)
class ScrapeCommand(GeneratingCommand):
    """ Scrape given url, capturing text between capture_after and break_before.



    ##Syntax

    %(syntax)

    ##Description

    %(description)

    """

    logger = logging.getLogger('splunk.Scrape')
    SPLUNK_HOME = os.environ['SPLUNK_HOME']
    APP_NAME = 'TA-data_scrape'


    LOGGING_STANZA_NAME = 'python'
    LOGGING_FILE_NAME = "scrape.log"
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
    crawlElement = Option()
    sourcetype = Option()
    download_only = Option(validate=validators.Boolean())
    cache_files = Option(validate=validators.Boolean())
    use_cache = Option(validate=validators.Boolean())
    path_name = Option()
    index = Option()
    log_level = Option()

    delimiter = Option()

    download_path = None


    def normalize_input(self):
        '''

        change string values to boolean where appropriate
        :param config:
        :param self:
        :return:
        '''
        config = vars(self)['_options']
        self.logger.debug("normalizing: " +str(config))

        # Ensure config['mask'] is always a list to keep code simpler later on
        if self.mask:
            if ',' in self.mask:
                self.mask = self.mask.split(',')
            else:
                self.mask = [self.mask]

        if not self.delimiter:
            self.delimiter = ';'
        elif self.delimiter.lower() in ['none', '', 'ignore']:
            self.delimiter = None

        if not self.index:
            self.index = "main"

        if not self.path_name:
            self.download_path = os.path.join(os.path.dirname(LIBDIR), 'downloads')
        else:
            self.download_path = os.path.join(os.path.dirname(LIBDIR), 'downloads', 'path_name')

    def generate(self):

         #yield{'_time': time(), '_raw': 'foo'}

        self.logger.debug("starting command execution")

        if self.log_level:
            if self.log_level.lower() == "debug" or self.log_level == "DEBUG":
                self.logger.setLevel(logging.DEBUG)
                self.logger.debug("SET log level to debug")
            else:
                self.logger.setLevel(logging.INFO)

        self.normalize_input()

        # windows support below
        #download_path = 'C:\\Program Files\\Splunk\\etc\\apps\\TA-data_scrape\\bin\\downloads'


        if not self.use_cache:
            if not os.path.exists(self.download_path):
                os.mkdir(self.download_path)

            if self.crawl and self.url:
                self.crawl_url()

            elif not self.crawl and self.url:
                parsed_url = urlparse.urlparse(self.url)
                self.download_file(self.download_path, self.url, self.mask, self.download_only)

        files = self.get_file_list()

        if not files:
            if not self.url:
                yield {'_time': time(), '_raw': 'No URL specified and no cached content found'}
            else:
                yield {'_time': time(), '_raw': 'No content to retrieve from ' + str(self.url)}


        files_processed_count = 0
        self.logger.debug("we have downloaded " + str(len(files)) + " files")

        if not self.download_only:
            for file_name in files:
                events = self.parse_events(file_name)
                output = self.format_output(events)

                if output:

                    if self.sourcetype:
                        yield {'_time': time(), '_raw': output, 'sourcetype': self.sourcetype}
                    else:
                        #self.logger.debug("yielding output for file:" + str(file_name))
                        yield {'_time': time(), '_raw': output}
                    files_processed_count = files_processed_count + 1
                else:
                    yield {'_time': time(), '_raw': 'no output parsed from:' + file_name}

        else:
            for fn in files:
                yield {'_time': time(), '_raw': 'downloaded ' + '/' + self.download_path + fn}

        sleep(1)
        if not self.cache_files:
            self.clean_output()


    def crawl_url(self):
        """
            Starting with config['url'] and crawl any additional pages until we reach a target.
            Target pages have no embedded links
        :param self:
        :return:
        """
        links = None
        if not self.url:
            return

        self.logger.debug("find_all_downloads begin with:" + str(self.url))
        links = self.get_page_links(self.url, self.mask)
        if not links:
            # no links found on page, we must have found a download target
            parsed_url = urlparse.urlparse(self.url)
            self.download_file(self.download_path, self.url, self.mask, self.download_only)
            sleep(0.2)

        while links:

            url = links.pop()
            self.logger.debug(" looking at page: " + url)
            mask = self.get_url_mask(self.url)
            if mask is None:
                self.logger.debug("mask is none, skip url " + url)
                continue
            new_links = self.get_page_links(url, "")

            if not new_links:
                self.download_file(self.download_path, url, mask, self.download_only)
                sleep(0.2)
            else:
                self.logger.debug(" page " + url + " had links " + str(new_links))
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
        self.logger.debug("trying to download:" + str(download_path) + ","+str(url)+"," +str(mask) + ","+str(download_only))
        filename = ''
        try:
            mask = self.get_url_mask(url)
            if not mask:
                if '/' in url:
                    mask = url.split('/')[-2]
                    if mask:
                        filename = download_path + '/' + url.split(mask)[1][0:].replace('/', '')
                    else:
                        filename = download_path + '/' + url.replace('/', '')
                else:
                    filename = download_path + '/' + url.replace('/', '')

        except ValueError:
            print("failed to generate filename for {0}, {1}".format(url, mask))
            sys.exit(1)
        except TypeError:
            print("TypeError formulating filename")
            sys.exit(1)
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
            file_handle.write("url: "+str(url))
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
        if not url:
            return []
        self.logger.debug("looking for links on page: " + str(url) + ", " + str(href_mask))
        if url.rfind('.') > url.rfind('/'):  # url ends with . + file type; is not a web directory name
            page_type = url[url.rfind('.')+1:]

            if page_type.lower() == 'pdf' or page_type.lower() == 'csv' or page_type.lower() == 'txt' or \
                    page_type.lower() == 'jpg' or page_type.lower() == 'gif':
                return None

        try:
            html_document = urllib2.urlopen(url)
        except urllib2.HTTPError as e:
            print(str(e.errno) + " HTTP ERROR RETURNED FROM URL " + str(url))
            sys.exit(3)
        except urllib2.URLError as e:
            print(e.reason + ": url was " + str(url))
            sys.exit(4)

        soup = BeautifulSoup(html_document.read(), 'html.parser')
        links = []
        formatted_links = []

        for link in soup.find_all('a'):
            links.append(link.get('href'))
        if not links:
            return None
        u = urlparse.urlparse(url)
        #self.logger.debug("found links:" + str(links))
        # find correct mask
        # #self.logger.debug("found these links:" + str(links))
        links = self.filter_links(links)
        self.logger.debug("filtered links are:" + str(links))
        if not links:
            return []

        for item in links:
            if item[0] == '/':  # href is relative!
                formatted_links.append(u.scheme + "://" + u.netloc + item)
            else:
                formatted_links.append(item)
        return formatted_links


    def filter_links(self, links):
        """
        :param links: list of strings representing urls
        :return:
        """
        self.logger.debug("filtering links using mask: " + str(self.mask))

        filtered_links = []
        if not links:
            return None

        self.logger.debug(" iterating through links to filter")
        for item in links:
            if item:

                # TODO use config['mask'] here I think...
                # if '/Elections/Resources/Files/htm' in item or '/Elections/Results' in item:
                for mask in self.mask:
                    if mask in item:
                        filtered_links.append(item)
        self.logger.debug("found these links after filtering: " + str(filtered_links))
        return filtered_links


    def get_url_mask(self, url):
        """
        Get the part of the url that is most significant, mainly used for building filename of output
        :param url:
        :return:
        """

        if not url or not self.mask:
            return None

        if isinstance(self.mask, list):
            for item in self.mask:
                if item in url:
                    return item

        elif isinstance(self.mask, str):
            if self.mask in url:
                return self.mask

    def get_file_list(self):
        """
        :return:
        """
        try:
            files = os.listdir(self.download_path)
        except OSError as error:
            self.logger.error("Unable to find downloaded files in path, try not using use_cache option " + str(self.download_path) + ", error " +
                              str(error.errno) )
            sys.exit(1)

        full_path = []
        for item in files:
            full_path.append(self.download_path + '/' + item)
        return full_path


    def parse_events(self, file_name):
        """

        :param file_name:
        :return:
        """
        
        #TODO cant assume breaks are only meaningful text on line...
        # capture text on same line but after start_before and before break_after string!!

        output = ''
        self.logger.debug("parsing " + str(file_name))

        try:
            with open(file_name, 'r') as fh:

                line = fh.readline()

                if self.capture_after:
                    while self.capture_after not in line and line:
                        if len(line) == 0:
                            output = None
                            print(str(file_name) + " did not find event break begin " + self.capture_after)
                        line = fh.readline()

                if self.break_before:
                    line = fh.readline()
                    while self.break_before not in line and line:
                        if len(line) == 0:
                            output = None
                            print(str(file_name) + " did not find event break end " + self.break_before)
                            break
                        output = output + line
                        line = fh.readline()

                if not self.break_before:
                    line = fh.readline()
                    while line:
                        output = output + line
                        line = fh.readline()

        except Exception as e:
            self.logger.info("exception parsing event occurred" + str(e))
        return output

    def format_output(self, blob):
        """
        Convert 2+ whitespace to ;
        :param blob:
        :return:
        """
        delim = self.delimiter
        if delim is None:
            return blob
        if blob is None:
            return "None"

        blob = re.sub(r'\n', delim, blob)
        blob = re.sub(r'\s*\.  +', delim, blob).strip()
        blob = re.sub(r'\s{2,}', delim, blob).strip()
        blob = re.sub(r'\s\.' + delim, delim, blob).strip()
        blob = re.sub(r'\.' + delim, delim, blob).strip()
        blob = re.sub(r'' + delim + '{2,}', delim, blob).strip()

        return blob

    def clean_output(self):
        """
            Remove all downloaded files
        :return:
        """
        for item in os.listdir(self.download_path):
            path = os.path.join(self.download_path, item)
            if os.path.isfile(path):
                os.remove(path)
        try:
            os.rmdir(self.download_path)
        except OSError as error:
            self.logger.info("could not clean up any cached files" + str(self.download_path) + ":"+str(error))

dispatch(ScrapeCommand, sys.argv, sys.stdin, sys.stdout, __name__)
 