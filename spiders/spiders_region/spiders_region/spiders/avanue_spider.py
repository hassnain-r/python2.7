import re
import json
from HTMLParser import HTMLParser

from scrapy.spiders import Request, CrawlSpider
from w3lib.url import add_or_replace_parameter, url_query_parameter


class AvenueSpider(CrawlSpider):
    name = "avenue_spider"
    color_ids_regex = 'swatch/\d+.(.+)-SW.jpg'
    color_ids_css = 'ul.Color a ::attr(style)'
    color_url_api = "https://www.avenue.com/en_US/product-variation?"
    images_api = 'https://www.avenue.com/dw/image/v2/AAMJ_PRD/on/demandware.static/-/Sites-avenue-master-catalog/' \
                 'default/images/large/'
    country_code_api = "https://www.avenue.com/on/demandware.store/Sites-Avenue-Site/en_US/51Integration-SetCountry?"

    deny_url = ["/en_US/plus-size-clothing/tops-knit-tops/#prefn1=size&prefv1=30%7C32&hcgid=tops-knit-tops"]

    def __init__(self, country="", currency="", **kwargs):
        super(AvenueSpider, self).__init__(**kwargs)
        self.start_urls = [
            'https://www.avenue.com/',
        ]

        self.country = "%s" % country
        self.currency = "%s" % currency

    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko)'
                      ' Chrome/55.0.2883.95 Safari/537.36',
        'DOWNLOAD_DELAY': 2.5
    }

    def parse(self, response):
        for country, currency in zip(self.country.split(','), self.currency.split(',')):
            yield Request(url="{}country={}&currency={}".format(self.country_code_api, country, currency),
                          dont_filter=True, callback=self.parse_start_page)

    def parse_start_page(self, response):
        raw_constant = ''.join(response.headers.getlist('Set-Cookie'))
        currency_constant = re.findall('\d+\.?\d+', raw_constant)[0]
        yield Request(url=self.start_urls[0], meta={"currency_constant": currency_constant},
                      callback=self.parse_categories)

    def parse_categories(self, response):
        sub_categories = response.css("ul.level-3 li a ::attr(href)").extract()
        for sub_category in sub_categories:

            if sub_category in self.deny_url:
                continue
            yield Request(url=sub_category, meta=response.meta.copy(),
                          callback=self.parse_pagination)

    def parse_pagination(self, response):
        product_urls = response.css('.product-image a ::attr(href)').extract()
        for product_url in product_urls:
            yield Request(url=product_url, meta=response.meta.copy(), callback=self.parse_product)

        raw_url = response.css('.infinite-scroll-placeholder ::attr(data-grid-url)').extract_first()
        if raw_url:
            yield Request(url=HTMLParser().unescape(raw_url), callback=self.parse_pagination)

    def parse_product(self, response):
        garment = {}
        raw_details = self.raw_details(response)
        garment["currency_constant"] = response.meta["currency_constant"] 
        pid = self.product_id(response)
        garment["skus"] = {}
        garment["price"] = raw_details["product_sales_price_ave"]
        garment["previous_price"] = raw_details["product_standard_price_ave"]
        garment["product_id"] = pid
        garment['url'] = self.product_url(response)
        garment['original_url'] = response.url
        garment["product_name"] = self.product_name(response)
        garment["product_brand"] = raw_details["storefront_name_ave"]
        garment["product_category"] = self.product_category(response)
        garment["product_gender"] = "Women"
        garment["currency"] = raw_details["current_currency_code_ave"]
        garment["product_description"] = self.product_description(response)
        garment["requests"] = []
        garment["image_urls"] = self.image_urls(response, pid)
        garment["requests"].extend(self.colour_requests(response, pid, garment))

        return self.next_request_or_garment(garment)

    def colour_requests(self, response, pid, garment):
        color_ids = self.color_ids(response)
        color_id_key = "{}_{}_{}".format("dwvar", pid, "color")

        return [Request(url="{}{}={}&pid={}&format=ajax".format(self.color_url_api, color_id_key, color_id, pid),
                        dont_filter=True, meta={"garment": garment}, callback=self.parse_colors)
                for color_id in color_ids]

    def parse_colors(self, response):
        garment = response.meta["garment"]
        garment['requests'].extend(self.size_requests(response, garment))

        return self.next_request_or_garment(garment)

    def size_requests(self, response, garment):
        css = 'ul.size a.swatchanchor ::attr(href)'
        available_sizes = response.css(css).extract()

        return [Request(url="{}&format=ajax".format(size_url), dont_filter=True, meta={"garment": garment},
                        callback=self.parse_sizes) for size_url in available_sizes]

    def parse_sizes(self, response):
        garment = response.meta["garment"]
        variant_urls = self.variant_urls(response)
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

    def product_pricing(self, response, garment):
        size_css = 'ul.size li.selected-value ::text'
        size = response.css(size_css).extract_first().strip()
        color = response.css('div.selected-value ::text').extract_first().strip()
        price, previous_price, currency = float(garment["price"]), float(garment["previous_price"]), garment["currency"]
        currency_constant = float(garment["currency_constant"])

        sku = {
            "size": size,
            "colour": color,
            "price": round(price * currency_constant, 2),
            "currency": currency,
            "previous_price": round(previous_price * currency_constant, 2)
            }

        return sku

    def skus(self, response, garment):
        skus = {}
        sku = self.product_pricing(response, garment)

        if self.variant_urls(response):
            raw_variant = response.css('ul.range li.selected ::text').extract()
            variant = ''.join(raw_variant).strip()
            sku["size"] = "{}/{}".format(sku["size"], variant)
        new_size = sku["size"]
        sku_id = "{}_{}".format(sku["colour"], new_size)
        skus[sku_id] = sku

        return skus

    def color_ids(self, response):
        color_ids = response.css(self.color_ids_css).extract()
        return [re.findall(self.color_ids_regex, color_id)[0] for color_id in color_ids]

    def image_urls(self, response, pid):
        color_code = self.color_ids(response)
        thumbnail_images = response.css('.productthumbnail ::attr(src)').extract()
        images = [image.split('?')[0] for image in thumbnail_images]

        return ["{}{}_{}.jpg?".format(self.images_api, pid, color) for color in color_code]+images

    def variant_urls(self, response):
        return response.css('ul.range a.swatchanchor ::attr(href)').extract()

    def product_url(self, response):
        url = response.css('link[rel="canonical"] ::attr(href)').extract_first()
        return response.urljoin(url)

    def product_id(self, response):
        return response.css('div.product-tile ::attr(data-itemid)').extract_first()

    def product_name(self, response):
        return response.css('h1.product-name span ::text').extract_first()

    def product_category(self, response):
        return response.css('ul.breadcrumb a ::text').extract()[1:]

    def product_description(self, response):
        raw_description = response.css('.copy-ctn-sec ::text').extract()
        return [' '.join(raw_description).split('var masterID')[0].strip()]

    def raw_details(self, response):
        raw_json = response.xpath('//script[contains(text(),"data_ave")]/text()').extract_first()
        raw_data = " ".join(raw_json.split())
        raw_data = re.findall('data_ave = (.+});', raw_data)[0]
        return json.loads(raw_data)

    def next_request_or_garment(self, garment):
        if garment['requests']:
            return garment['requests'].pop()
        del garment["requests"]

        return garment

