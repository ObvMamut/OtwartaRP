from otwarta.scrapers.sites.dorzeczy import DoRzeczyAsyncScraper
from otwarta.scrapers.sites.pch24 import PCH24AsyncScraper

SITE_ADAPTERS = {
    "dorzeczy": DoRzeczyAsyncScraper,
    "pch24": PCH24AsyncScraper,
}
