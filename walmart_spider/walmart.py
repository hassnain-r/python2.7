import json
import re
from scrapy.spiders import CrawlSpider, Request


class WalMart(CrawlSpider):

    name = "walmart_spider"
    start_urls = ["https://www.walmart.ca/en/clothing-shoes-accessories/men/N-2108"]
    allowed_domains = ['www.walmart.ca']

    custom_settings = {
        "USER_AGENT": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/64.0.3282.167 Safari/537.36",
        "DOWNLOAD_DELAY": 2.5,
    }

    def parse(self, response):
        yield Request(url=self.start_urls[0], callback=self.parse_categories)

    def parse_categories(self, response):
        trail = self.add_trail(response)
        categories = response.css('ul.l-3 a ::attr(href)').extract()
        for category in categories:
            yield Request(url=response.urljoin(category), meta={"trail": trail}, callback=self.parse_pagination)

    def parse_pagination(self, response):
        trail = self.add_trail(response)
        product_urls = response.css('a.product-link ::attr(href)').extract()
        for product_url in product_urls:
            yield Request(url=response.urljoin(product_url), meta={"trail": trail}, callback=self.parse_product)

        next_page = response.css('a#loadmore ::attr(href)').extract_first()
        if next_page:

            yield Request(url=response.urljoin(next_page), meta={"trail": trail}, callback=self.parse_pagination)

    def parse_product(self, response):
        garment = {}
        pid = self.product_id(response)
        garment["product_id"] = pid
        garment["trail"] = self.add_trail(response)
        garment["product_name"] = self.product_name(response)
        garment["brand"] = self.product_brand(response)
        garment["product_category"] = self.product_category(response)
        garment["gender"] = "Men"
        garment["url"] = self.product_url(response)
        garment["original_url"] = response.url
        garment["image_urls"] = self.image_urls(response)
        garment["skus"] = self.skus(response)
        garment["product_description"] = self.product_description(response)
        return garment

    def add_trail(self, response):
        return "{}{}".format(response.meta.get('trail', []), [response.url])

    def product_id(self, response):
        return response.css('.productRollupID::attr(value)').extract_first()

    def product_name(self, response):
        return response.css('h1[itemprop="name"] ::text').extract_first()

    def product_brand(self, response):
        return response.css('.brand a::text').extract_first()

    def product_category(self, response):
        return response.css('#breadcrumb span::text').extract()[1:-1]

    def product_url(self, response):
        url = response.css('link[rel="canonical"] ::attr(href)').extract_first()
        return response.urljoin(url)

    def image_urls(self, response):
        raw_json = response.xpath('//script[contains(text(),"enlargedURL")]/text()').extract_first()
        images = re.findall('enlargedURL : (.+")', raw_json)
        return ["https:{}".format(image).replace('"', '') for image in images]

    def product_description(self, response):
        xpath = '//*[contains(@class, "productDescription") and contains(., "Description & Features")]' \
                '//*[contains(@class, "description")]//text()'
        return response.xpath(xpath).extract()

    def skus(self, response):
        skus = {}
        raw_json = response.xpath('//script[contains(text(),"variantDataRaw")]/text()').extract_first()
        raw_json = re.findall('variantDataRaw : (.+\])', raw_json)[0]
        raw_skus = json.loads(raw_json)

        for raw_sku in raw_skus:
            price, previous_price = raw_sku.get('price_store_price')[0], raw_sku.get('price_store_was_price')
            currency = response.css('[itemprop=priceCurrency] ::attr(content)').extract_first()

            sku = {
                "price": round(float(price), 2),
                "previous_price": round(float(previous_price[0]), 2) if previous_price else previous_price,
                "currency": currency,
            }

            colour = raw_sku.get('variantKey_en_Colour') or raw_sku.get('variantKey_en_Actual_Color')
            if colour:
                sku['colour'] = colour[0]

            size = raw_sku.get('variantKey_en_Size')
            sku["size"] = size[0] if size else "One Size"
            is_available = raw_sku.get('online_status')

            if is_available[0] == "70":
                sku["out_of_stock"] = True

            skus[raw_sku['upc_nbr'][0]] = sku
        return skus

