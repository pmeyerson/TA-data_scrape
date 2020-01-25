#!/usr/bin/env python
from __future__ import print_function
import logging
import logging.handlers
import os
import re
import sys
import six

if sys.version_info >= (3, 0):
    print("version 3.x")
else:
    print("version 2.x")


LIB_DIR = os.path.join(os.path.join(os.path.dirname(__file__), ".."), "lib")

if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

try:
    import urllib2
    import urlparse
    from future.moves.urllib.request import urlopen
    from time import sleep, time
    import bs4
    from bs4 import BeautifulSoup, SoupStrainer
    from splunklib.searchcommands import (
        dispatch,
        GeneratingCommand,
        Configuration,
        Option,
        validators,
    )

except ImportError:
    print("Unable to import modules from " + LIB_DIR)
    sys.exit(1)


class Error(Exception):
    pass


class HtmlElementNotFound(Error):
    """Raised when crawlElement is specified but soup.find(id=self.crawlElement) is null"""

    pass


@Configuration(type="events", retainsevents=True, streaming=False)
class ScrapeCommand(GeneratingCommand):
    """ Scrape given url, capturing text between capture_after and break_before.

    ##Syntax
    %(syntax)
    ##Description
    %(description)

    """

    logger = None
    url = Option()
    mask = Option()  # required URL fragment
    ignore_urls = (
        Option()
    )  # not implemented yet; url fragment to ignore for crawling (navigation, banner, etc)
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
    list_paths = Option()
    index = Option()
    log_level = Option()
    delimiter = Option()
    download_path = None
    clean = Option()  # not implemented yet

    def setup_logger(self):
        """
            Setup splunk logging options per Splunk example.
            Log to $SPLUNK_HOME/var/log/splunk
        """
        self.logger = logging.getLogger("splunk.scrape")
        splunk_home = os.environ["SPLUNK_HOME"]
        app_name = "TA-scrape"
        logging_file_name = app_name + ".log"
        base_log_path = os.path.join("var", "log", "splunk")
        logging_format = (
            "%(asctime)s %(levelname)-s\t%(module)s:%(lineno)d - %(message)s"
        )
        splunk_log_handler = logging.handlers.RotatingFileHandler(
            os.path.join(splunk_home, base_log_path, logging_file_name), mode="a"
        )
        splunk_log_handler.setFormatter(logging.Formatter(logging_format))
        self.logger.addHandler(splunk_log_handler)
        if self.log_level:
            if self.log_level.lower() == "debug" or self.log_level == "DEBUG":
                self.logger.setLevel(logging.DEBUG)
                self.logger.debug("SET log level to debug")
            else:
                self.logger.setLevel(logging.INFO)

    def normalize_input(self):
        """
            Change string values to boolean where appropriate and set default values for delimiter and index
        """
        config = vars(self)["_options"]
        self.logger.debug("normalizing: " + str(config))

        # Ensure config['mask'] is always a list to keep code simpler later on in get_url_mask()
        if self.mask:
            if "," in self.mask:
                self.mask = str(self.mask).split(",")
            else:
                self.mask = [self.mask]

        if not self.delimiter:
            self.delimiter = ";"

        elif self.delimiter.lower() in ["none", "", "ignore"]:
            self.delimiter = None

        if not self.index:
            self.index = "main"

        if not self.path_name:
            self.download_path = os.path.join(
                os.path.dirname(os.path.dirname(LIB_DIR)), "downloads"
            )
        else:
            self.download_path = os.path.join(
                os.path.dirname(os.path.dirname(LIB_DIR)), "downloads", "path_name"
            )

    def generate(self):
        """
           Main method called by GeneratingCommand class.
        """

        self.setup_logger()
        self.logger.debug("starting command execution")
        self.normalize_input()
        target_urls = None

        if self.list_paths:
            self.get_download_paths()
            sys.exit(0)

        if not self.use_cache:
            if not os.path.exists(self.download_path):
                os.mkdir(self.download_path)

            if self.crawl and self.url:
                target_urls = self.crawl_url()

            elif not self.crawl and self.url:
                target_urls = [urlparse.urlparse(self.url)]

        # download content if caching enabled
        if self.cache_files:
            self.download_files(self.download_path, target_urls)
        #
        files = self.get_file_list()

        if not files:
            if not self.url:
                yield {
                    "_time": time(),
                    "_raw": "No URL specified and no cached content found",
                }
                return
            else:
                yield {
                    "_time": time(),
                    "_raw": "No content to retrieve from " + str(self.url),
                }
                return

        files_processed_count = 0
        self.logger.debug("we have downloaded " + str(len(files)) + " files")

        if self.download_only:
            for fn in files:
                yield {
                    "_time": time(),
                    "_raw": "downloaded " + "/" + self.download_path + fn,
                }

        else:
            for file_name in files:
                events = self.parse_events(file_name)
                output = self.format_output(events)

                if output:

                    if self.sourcetype:
                        yield {
                            "_time": time(),
                            "_raw": output,
                            "sourcetype": self.sourcetype,
                        }
                    else:
                        # self.logger.debug("yielding output for file:" + str(file_name))
                        yield {"_time": time(), "_raw": output}

                    files_processed_count = files_processed_count + 1

                else:
                    yield {
                        "_time": time(),
                        "_raw": "no output parsed from:" + file_name,
                    }

        sleep(1)
        if not self.cache_files:
            self.clean_output()

    def crawl_url(self):
        """
            Starting with self.url and crawl any additional pages until we reach a target.
            Target pages have no embedded links
        :return:    list of identified target urls (without any links on them)
        """
        target_urls = []
        if not self.url:
            return

        self.logger.debug("find_all_downloads begin with:" + str(self.url))
        links = self.get_page_links(self.url, self.mask)
        if not links:
            # no links found on page, we must have found a download target
            target_urls.append(self.url)

        while links:

            url = links.pop()
            self.logger.debug(" looking at page: " + url)
            interesting = self.get_url_mask(
                self.url
            )  # determine if current url is interesting or not

            if interesting:

                new_links = self.get_page_links(url, "")

                if new_links:
                    self.logger.debug(" page " + url + " had links " + str(new_links))
                    links.extend(new_links)
                else:
                    target_urls.append(url)

            elif not interesting:
                self.logger.debug("skipping masked discovered url=" + url)
                continue

        return target_urls

    def download_file(self, download_path, urls):
        """
        Downloads html content at the given url. and saves the file locally.
        :param download_path:
        :param urls:

        """
        for url in urls:

            self.logger.debug(
                "trying to download:" + str(download_path) + "," + str(url)
            )
            filename = self.format_filename(url, download_path)
            data = self.read_url(url)

            with open(filename, "w") as file_handle:
                file_handle.write("url: " + str(url))
                file_handle.write(data)

    def format_filename(self, url, download_path):
        """
            Create the filename based on the URL provided.
            https://www.election.com/2018/precinct1.html = precint1.html

            @param url:             The url being downloaded
            @parm download_path:     Local path
            
        """
        filename = None
        try:
            mask = self.get_url_mask(url)
            if not mask:

                if "/" in url:
                    mask = url.split("/")[-2]

                    if mask:
                        filename = (
                            download_path
                            + "/"
                            + url.split(mask)[1][0:].replace("/", "")
                        )
                    else:
                        filename = download_path + "/" + url.replace("/", "")
                else:
                    filename = download_path + "/" + url

        except ValueError:
            print("failed to generate filename for {0}".format(url))
            sys.exit(1)
        except TypeError:
            print("TypeError formulating filename")
            sys.exit(1)

        return filename

    @staticmethod
    def read_url(url):
        """

        :param url:
        :return:
        """
        url_handle = None
        try:
            url_handle = urllib2.urlopen(url)
        except urllib2.HTTPError as error:
            print(
                "url read failed for {0}: {1} {2}".format(url, error.code, error.reason)
            )
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

        if url.rfind(".") > url.rfind(
            "/"
        ):  # url ends with . + file type; is not a web directory name
            page_type = url[url.rfind(".") + 1:]

            if (
                page_type.lower() == "pdf"
                or page_type.lower() == "csv"
                or page_type.lower() == "txt"
                or page_type.lower() == "jpg"
                or page_type.lower() == "gif"
            ):
                return None

        html_document = self.read_url(url)
        only_a_tags = SoupStrainer("a")

        soup = BeautifulSoup(
            html_document.read(), "html.parser", parse_only=only_a_tags
        )
        links = []
        formatted_links = []

        for link in soup.find_all("a"):
            links.append(link.get("href"))
        if not links:
            return None
        u = urlparse.urlparse(url)
        links = self.filter_links(links)
        self.logger.debug("filtered links are:" + str(links))
        if not links:
            return []

        for item in links:
            if item[0] == "/":  # href is relative!
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

                for mask in self.mask:
                    if mask in item:
                        filtered_links.append(item)
        self.logger.debug("found these links after filtering: " + str(filtered_links))
        return filtered_links

    def get_url_mask(self, url):
        """
        Get the part of the url that is most significant, mainly used for building filename of output
        :param url:
        :return:  the element of self.mask which was part of the url.
        """

        if not url or not self.mask:
            return None

        if isinstance(self.mask, str):
            self.mask = [self.mask]

        if isinstance(self.mask, list):
            for item in self.mask:
                if item in url:
                    return item

    def get_file_list(self):
        """
        :return:
        """
        try:
            files = os.listdir(self.download_path)
        except OSError as error:
            self.logger.error(
                "Unable to find downloaded files in path, try not using use_cache option "
                + str(self.download_path)
                + ", error "
                + str(error.errno)
            )
            sys.exit(1)

        full_path = []
        for item in files:
            full_path.append(self.download_path + "/" + item)
        return full_path

    def get_download_paths(self):
        """
        List all subdirectories within /downloads and yield each as event data.
        """
        try:
            download_root = os.path.join(
                os.path.dirname(os.path.dirname(LIB_DIR)), "downloads"
            )
        except OSError as error:
            self.logger.error(
                "Unable to find downloaded files in path, try not using use_cache option "
                + str(self.download_path)
                + ", error "
                + str(error.errno)
            )
            sys.exit(1)
        try:
            content = os.listdir(download_root)
        except FileNotFoundError:
            self.logger.error(
                "Unable to list contents of path=" + download_root + ", aborting."
            )
            sys.exit(1)

        if not content:
            yield {
                "_time": time(),
                "_raw": "Only the default 'downloads' cache path exists.",
            }

        for item in content:
            if os.path.isdir(item):
                yield {"_time": time(), "_raw": item}

    def parse_events(self, file_name):
        """

        :param file_name:
        :return:
        """

        # TODO cant assume breaks are only meaningful text on line...
        # capture text on same line but after start_before and before break_after string!!

        output = ""
        self.logger.debug("parsing " + str(file_name))

        try:
            with open(file_name, "r") as fh:

                if self.crawlElement:
                    data = fh.read()

                    soup = BeautifulSoup(data, "html.parser")
                    output = soup.find(id=self.crawlElement)

                    if not output:
                        error_str = (
                            "HTML element "
                            + self.crawlElement
                            + " not found at url "
                            + self.url
                        )
                        raise HtmlElementNotFound(error_str)

                    output.smooth()
                    output = output.renderContents()
                    return output

                line = fh.readline()

                if self.capture_after:
                    while self.capture_after not in line and line:
                        if len(line) == 0:
                            output = None
                            print(
                                str(file_name)
                                + " did not find event break begin "
                                + self.capture_after
                            )
                        line = fh.readline()

                if self.break_before:
                    line = fh.readline()
                    while self.break_before not in line and line:
                        if len(line) == 0:
                            output = None
                            print(
                                str(file_name)
                                + " did not find event break end "
                                + self.break_before
                            )
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

        self.logger.debug("formatting " + str(blob))
        delim = self.delimiter
        if delim is None:
            return blob
        if blob is None:
            return "None"

        blob = re.sub(r"\n", delim, blob)
        blob = re.sub(r"\s*\.  +", delim, blob).strip()
        blob = re.sub(r"\s{2,}", delim, blob).strip()
        blob = re.sub(r"\s\." + delim, delim, blob).strip()
        blob = re.sub(r"\." + delim, delim, blob).strip()
        blob = re.sub(r"" + delim + "{2,}", delim, blob).strip()

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
            self.logger.info(
                "could not clean up any cached files"
                + str(self.download_path)
                + ":"
                + str(error)
            )


dispatch(ScrapeCommand, sys.argv, sys.stdin, sys.stdout, __name__)
