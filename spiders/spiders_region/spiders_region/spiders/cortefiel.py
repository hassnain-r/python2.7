from .base import DemandwareBaseSpider


class CortefielSpider(DemandwareBaseSpider):
    start_urls = ["https://cortefiel.com/"]
    allowed_domains = ["cortefiel.com"]

    rotate_user_agent = True
    colour_api = "https://cortefiel.com/on/demandware.store/Sites-CTF-Site/es_ES/Product-Variation?" \
                 "pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"

    name = "cortefiel_spider"

    custom_css = {"colour_link_css": ".c02__swatch-list a ::attr(href)",
                  "size_url_css": ".size-list a ::attr(href)",
                  "colour_text_css": ".c02__color-description span ::text",
                  "size_text_css": ".c02__size-description span ::text",
                  "images_css": 'dataimage ::attr(data-image-zoom)',
                  "name_css": 'h1[class="c02__product-name"] ::text',
                  }
