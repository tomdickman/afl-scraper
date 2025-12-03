# AFL Scraper - Scraper

This module is solely responsible for fetching required pages, so that the page data may be parsed to extract the data within.

The only CSS selectors and other site information to be maintained here is anything required to scrape a specific page, like navigating to the page in question. The playwright `page` can then be used by parser to extract required data.
