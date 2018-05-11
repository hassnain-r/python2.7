from .base import DemandwareBaseSpider


class AvenueSpider(DemandwareBaseSpider):
    start_urls = ["https://www.avenue.com/en_US"]
    allowed_domains = ["www.avenue.com"]

    rotate_user_agent = True
    colour_api = "https://www.avenue.com/en_US/product-variation?" \
                 "pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"

    name = "big_avenue"

    custom_css = {
        "name_css": "h1.product-name span ::text",
        "sale_price_css": '//div[contains(@class, "sales")]//ins/text()'
    }
