from unittest import TestCase

from scripts.rss_feed_validator import RSSFeedValidator


class TestRSSFeedValidator(TestCase):
    def test_validate_feed(self):
        rss_feed_validator = RSSFeedValidator()
        feed = rss_feed_validator.validate_feed("https://comiccaster.xyz/rss/farside-daily", "farside")
        print(feed.caption)
        feed = rss_feed_validator.validate_feed("https://comiccaster.xyz/rss/the-worried-well", "worried-well")
        print(feed.caption)
        feed = rss_feed_validator.validate_feed("https://xkcd.com/atom.xml", "xkcd")
        print(feed.caption)

