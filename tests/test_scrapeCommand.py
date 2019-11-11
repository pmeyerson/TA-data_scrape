from unittest import TestCase
import pytest
import bin.datascrape as datascrape


class TestScrapeCommand(TestCase):

    datascraper = datascrape.ScrapeCommand()

    def test_format_output(self):

        output = datascrape.ScrapeCommand.format_output("x  y", None)
        assert output == "x  y"

        output = datascrape.ScrapeCommand.format_output(None, ",")
        assert output is None

        output = datascrape.ScrapeCommand.format_output("x  y", ";")
        assert output == "x;y"

        output = datascrape.ScrapeCommand.format_output("x\ny", ';')
        assert output == "x;y"

        output = datascrape.ScrapeCommand.format_output("x .;y", ';')
        assert output == "x;y"

        output = datascrape.ScrapeCommand.format_output("x;;y", ';')
        assert output == 'x;y'

    def test_parse_events(self):


        self.fail()

    def test_get_file_list(self):
        self.fail()

    def test_get_url_mask(self):

        output = datascrape.ScrapeCommand.get_url_mask(None, None)
        assert output is None

        output = datascrape.ScrapeCommand.get_url_mask("https://foo.com", None)
        assert output is None

        output = datascrape.ScrapeCommand.get_url_mask('https://foo.com/media', {'mask': 'media'})
        assert output == 'media'

        output = datascrape.ScrapeCommand.get_url_mask('https://foo.com/media', {'mask': 'storage'})
        assert output is None

        output = datascrape.ScrapeCommand.get_url_mask('https://foo.com/media', {'mask': ['storage', 'media']})
        assert output == 'media'

        output = datascrape.ScrapeCommand.get_url_mask('https://foo.com/media', {'mask': ['foo', 'bar']})
        assert output is None

    def test_filter_links(self):

        output = datascrape.ScrapeCommand.filter_links(['abc.com'], {})
        assert output is None

        output = datascrape.ScrapeCommand.filter_links([], {'mask': ['abc'])
        self.fail()

    def test_get_page_links(self):
        self.fail()

    def test_read_url(self):
        self.fail()

    def test_download_file(self):
        self.fail()

    def test_find_all_downloads(self):
        self.fail()

    def test_normalize_input(self):
        self.fail()

    def test_generate(self):
        self.fail()
