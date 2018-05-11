from .base import DemandwareBaseSpider


class TwoXUSpider(DemandwareBaseSpider):
    start_urls = ["https://www.uniqlo.com/"]
    allowed_domains = ["www.uniqlo.com"]

    rotate_user_agent = True
    colour_api = "https://www.uniqlo.com/on/demandware.store/Sites-EU-Site/en/Product-Variation?" \
                 "pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"

    name = "uniqlo_spider"

    custom_css = {
        "categories_xpath": '//li[@class="parbase navLink section"]//a/@href',
        "colour_link_css": "ul.color .swatchanchor ::attr(data-seoproducturl-preventdefault)",
        "colour_text_css": "li.selected-value ::text",
        "size_url_css": "ul.size .swatchanchor ::attr(data-seoproducturl-preventdefault)",
        "size_text_css": "ul.size .selected span ::text",
        "image_css": "img.productthumbnail ::attr(src)",
        'name_css': 'h1[itemprop="name"] ::text',
        }
