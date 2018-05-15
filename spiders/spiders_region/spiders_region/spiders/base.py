import re
import json

from scrapy.spiders import CrawlSpider, Request
from HTMLParser import HTMLParser
from w3lib.url import url_query_parameter


class DemandwareCss(object):
    colour_link_css = "ul.Color .swatchanchor ::attr(href), ul.color .swatchanchor ::attr(href)"
    colour_text_css = "ul.Color li.selected a ::text"
    size_url_css = "ul.size .swatchanchor ::attr(href)"
    size_text_css = "ul.size li.selected a ::text"
    variant_url_css = 'ul.range .swatchanchor ::attr(href)'
    variant_text_css = 'ul.range li.selected a ::text'
    stock_availability_css = "ul.size .unselectable"
    p_price_xpath = '//span[contains(@class, "standard")]/text()'
    sale_price_css = '//span[contains(@class, "sale")]/text()'

    name_css = 'h1.product-name ::text'
    categories_xpath = '//ul[contains(@class, "level-3")]//a/@href'
    product_urls_xpath = '//div[contains(@class, "product-image")]//a/@href'
    infinite_scroll_css = '.infinite-scroll-placeholder ::attr(data-grid-url)'
    next_page_css = '//a[contains(@class, "next")]/@href'
    default_color_css = '.product-variations ::attr(data-current)'
    images_css = '.thumbnail-link ::attr(href)'
    breadcrumb_css = '//*[contains(@class, "breadcrum")]//a/text()'
    pid_xpath = '//script[contains(text(),"cq_params")]/text()'
    brand_xpath = '//script[contains(text(),"brand")]/text()'


class DemandwareBaseSpider(CrawlSpider):
    custom_css = {}

    def __init__(self, country="", currency="", **kwargs):
        self.css = DemandwareCss()
        self.css.__dict__.update(self.custom_css)

        super(DemandwareBaseSpider, self).__init__(**kwargs)
        self.country = "%s" % country
        self.currency = "%s" % currency

    def parse(self, response):
        yield Request(url="{}country={}&currency={}".format(self.country_code_api, self.country, self.currency),
                      dont_filter=True, callback=self.parse_homepage)

    def parse_homepage(self, response):
        yield Request(url=self.start_urls[0], callback=self.parse_categories)

    def parse_categories(self, response):
        categories = response.xpath(self.css.categories_xpath).extract()
        for category in categories:
            yield Request(url=response.urljoin(category), meta=response.meta.copy(),
                          callback=self.parse_pagination)

    def parse_pagination(self, response):
        product_urls = response.xpath(self.css.product_urls_xpath).extract()
        for product_url in product_urls:
            yield Request(url=response.urljoin(product_url), meta=response.meta.copy(), callback=self.parse_product)
        infinite_scroll = response.css(self.css.infinite_scroll_css).extract_first()
        next_page = response.xpath(self.css.next_page_css).extract_first()

        if next_page:
            yield Request(url=response.urljoin(next_page), callback=self.parse_pagination)

        elif infinite_scroll:
            yield Request(url=response.urljoin(HTMLParser().unescape(infinite_scroll)), callback=self.parse_pagination)

    def parse_product(self, response):
        garment = {}
        pid = self.product_id(response)

        if not pid:
            return
        garment["currency_constant"] = response.meta.get("currency_constant")
        garment["previous_price"] = self.raw_details(response)
        garment["product_id"] = pid
        garment['url'] = self.product_url(response)
        garment['original_url'] = response.url
        garment["product_name"] = self.product_name(response)
        garment["product_brand"] = self.product_brand(response)
        garment["product_category"] = self.product_category(response)
        garment["product_description"] = self.product_description(response)
        garment["skus"] = {}
        garment["image_urls"] = []
        garment["requests"] = []
        garment["requests"].extend(self.colour_requests(response, pid, garment))
        return self.next_request_or_garment(garment)

    def colour_requests(self, response, pid, garment):
        default_colour = self.default_colour(response)
        cids = self.color_ids(response, pid)
        if default_colour:

            cids.append(default_colour["color"]["value"])

        return [Request(url=self.colour_api.format(cid=cid, pid=pid), callback=self.parse_colour, dont_filter=True,
                        meta={"garment": garment}) for cid in cids if cid]

    def parse_colour(self, response):
        garment = response.meta["garment"]
        garment["image_urls"].extend(self.image_urls(response))
        garment['requests'].extend(self.size_requests(response, garment))

        return self.next_request_or_garment(garment)

    def size_requests(self, response, garment):
        size_urls = response.css(self.css.size_url_css).extract()

        return [Request(url="{}&format=ajax".format(size_url), dont_filter=True, meta={"garment": garment},
                        callback=self.parse_sizes) for size_url in size_urls if size_url]

    def parse_sizes(self, response):
        garment = response.meta["garment"]
        variant_urls = response.css(self.css.variant_url_css).extract()

        if variant_urls:
            garment["requests"].extend(self.variant_requests(variant_urls, garment))

        else:
            garment["skus"].update(self.skus(response, garment))
        return self.next_request_or_garment(garment)

    def variant_requests(self, variant_urls, garment):
        return [Request(url="{}&format=ajax".format(variant_url), dont_filter=True, meta={"garment": garment},
                        callback=self.parse_variants) for variant_url in variant_urls] if variant_urls else []

    def parse_variants(self, response):
        garment = response.meta["garment"]
        garment["skus"].update(self.skus(response, garment))

        return self.next_request_or_garment(garment)

    def skus(self, response, garment):
        skus = {}
        color = self.clean(response.css(self.css.colour_text_css).extract())[0]
        out_of_stock = response.css(self.css.stock_availability_css)
        raw_size = response.css(self.css.size_text_css).extract_first()
        price = self.clean(response.xpath(self.css.sale_price_css).extract_first())
        p_price = self.clean(response.xpath(self.css.p_price_xpath).extract_first())
        sku = {"price": price, "color": color}
        if p_price:
            sku["previous_price"] = p_price

        else:
            sku["previous_price"] = garment["previous_price"]

        if raw_size:
            sku["size"] = self.clean(raw_size)

        if response.css(self.css.variant_url_css):
            variant = response.css(self.css.variant_text_css).extract_first()
            sku["size"] = "{}/{}".format(sku["size"], variant)

        if out_of_stock:
            sku["out_of_stock"] = True

        skus["{}_{}".format(color, sku["size"])] = sku

        return skus

    def default_colour(self, response):
        colour_text = response.css(self.css.default_color_css).extract_first()

        if not colour_text:
            return

        return json.loads(colour_text)

    def color_ids(self, response, pid):
        colour_urls = response.css(self.css.colour_link_css).extract()+[response.url]
        return [url_query_parameter(color_url, 'dwvar_{}_color'.format(pid)) for color_url in colour_urls]

    def image_urls(self, response):
        image_urls = response.css(self.css.images_css).extract()
        return [response.urljoin(image_url) for image_url in image_urls]

    def product_name(self, response):
        return response.css(self.css.name_css).extract_first()

    def product_url(self, response):
        return response.css('link[rel="canonical"] ::attr(href)').extract_first()

    def original_url(self, response):
        return response.url

    def product_id(self, response):
        raw_pid = response.xpath(self.css.pid_xpath).extract_first()
        return re.findall("id: '(.*?)'", raw_pid)[0]

    def product_category(self, response):
        return response.xpath(self.css.breadcrumb_css).extract()

    def product_brand(self, response):
        brand_text = response.xpath(self.css.brand_xpath).extract_first()

        if brand_text:
            brand = re.findall('brand.\s?:\s?.?(.*?).,', ''.join(brand_text.split()))
            return brand[0] if brand else "No_Brand_Found"

    def next_request_or_garment(self, garment):
        if garment['requests']:
            return garment['requests'].pop()
        del garment["requests"]

        return garment

    def raw_details(self, response):
        return response.xpath(self.css.p_price_xpath).extract_first()

    def product_description(self, response):
        return []

    def clean(self, response):
        raw_text = response
        if isinstance(response, list):
            cleaned_list = [value.strip() for value in response if value]

            return [item for item in cleaned_list if item]

        if raw_text:
            return response.strip()
