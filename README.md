# TA-data_scrape
Splunk custom search command to perform simple text web scraping against a URL or against a crawled URL tree.  crawled and parsed content is used to generate events.  Events can be retained by appending  | outputlookup lookup_name

## Installation ## 

Download the latest release .spl file from the Releases tab, or clone this repository and move the TA-scrape subdirectory into your $SPLUNK_HOME/etc/apps.

## Usage ## 
``` | scrape url=https://www.google.com ```

  Default usage.

``` | scrape ```

  When used without the url paramater, any previously-cachced content will be parsed and output, then deleted.


## Parsing Arguments ##
<b>capture_after</b>: All characters prior to (inclusive) the given will be ignored.  Helpful to filter out junk metadata.

Example:
 ` | scrape capture_after=PRE `
  
  All content prior to the 'PRE' string (inclusive) is ignored.

<b>break_before</b>: All characters after (inclusive) the given will be ignored.  Helpful to filter out uninteresting text.
<br></br>Example: ` | scrape break_before=**  ` <p></p>
  All content after the string '**' (inclusive) is ignored.

<b>captureId</b>: ID name of HTML element to capture.  capture_after and break_before will be ignored.<br></br>
  Example: ` | scrape captureId=maincontent `
  <p></p>
  Content outside the html element maincontent will be ignored.


## Crawling and Caching Arguments ##

<b>crawl</b>: Boolean flag to indicate to enable searching for additional URLs to crawl through. Defaults to false.

Example: ` | scrape crawl = true ` <p></p>

  By default, any navigable URLS will be crawled for additional content.

<b>single_event_mode</b>: Boolean flag to indicate that only one event will be found on a crawled page. Defaults to false.
<br></br>Example: ` |scrape single_event_mode = true `<p></p>
  All content will be returned as a single event

<p><b>mask</b>:  One or more url fragments to require if scraping a tree of urls.
Any links that do not include the fragment(s) will not be crawled.  This can help avoid crawling
navigation/header links.

Example: ` | scrape mask=/Results/ `

  Content from URLS which do not include /Results/ in the URL will not generate events, but will be crawled per any parameters set.


Example2: ` | scrape mask="/Results,/Districts" ` </p>
 
  Content from URLS which do not include /Results or /Districts in the URL will not generate events; but will be cralwed per parameters set.
  
<b>download_only</b>: Boolean to indicate that files should be downloaded only and not ingested.  Defaults to false.
<br></br>Example: ` | scrape url=https://www.google.com download_only = true cache_files = true` <p></p>

  Content will be scraped from the url and cached for later parsing and eventing.

<b>path_name</b>:  Directory name to be used for saving crawled files; subdirectory of APP_PATH/bin/downloads.
If blank, data will be downloaded to APP_PATH/bin/downloads.<br></br>
Example: ` | scrape https://www.election2018.com path_name = elections2018 download_only = true cache_files = true` <p></p>

  Content from the URL will be downloaded to relative path 'elections2018' for later processing.

<b>use_cache</b>: Boolean to indicate we should only process already downloaded content.  Specify path_name if you
did so when you downloaded the data originally.  Otherwise content from APP_PATH/bin/downloads will be ingested.

Example: ` | scrape use_cache=true path_name = elections2018 ` <p></p>

  Content from cache 'elections2018' will be parsed and used to generate events.

<b>cache_files</b>:  Any downloaded files should be retained after parsing.  This can be useful to scrape content once while you work on perfecting the event parsing parameters to use.
Example: ` | scrape https://www.google.com cache_files = true ` <p></p></li><br></br>

## <b>Utility Arguments</b> ## 
<b>log_level</b>: Use DEBUG to increase log level.

Example: ` | scrape url=https://www.cnn.com log_level = DEBUG ` 

  DEBUG level logging will be used, see index=_internal 
  
## Support ##

Feel free to raise an issue for assistence or to report a bug.
If you encounter a bug please include your splunk version and python version for your server (if running Splunk 8)
</html>
