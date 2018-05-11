from .base import DemandwareBaseSpider


class TwoXUSpider(DemandwareBaseSpider):
    start_urls = ["https://www.2xu.com/"]
    allowed_domains = ["www.2xu.com"]

    rotate_user_agent = True
    colour_api = "https://www.2xu.com/on/demandware.store/Sites-txuUS-Site/en_US/Product-Variation?" \
                 "pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"
    name = "2xu_spider"

