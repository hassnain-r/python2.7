from .base import DemandwareBaseSpider


class JohnVarvatos(DemandwareBaseSpider):
    start_urls = ["https://www.johnvarvatos.com/"]
    allowed_domains = ["www.johnvarvatos.com"]

    rotate_user_agent = True
    colour_api = "https://www.johnvarvatos.com/product?pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"
    name = "john_varvatos_spider"

    custom_css = {
        "size_url_css": "select#va-size option ::attr(value)",
        "size_text_css": 'option[selected="selected"] ::text',
        "categories_xpath": '//a[@role="menuitem"]/@href',
        "images_css": ".product-image img ::attr(src)",
        "colour_text_css": "ul.Color li.selected a ::attr(title)",
        }
