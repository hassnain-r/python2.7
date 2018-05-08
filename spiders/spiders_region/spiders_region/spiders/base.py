import re

from scrapy.spiders import CrawlSpider, Request
from HTMLParser import HTMLParser
from w3lib.url import url_query_parameter


class BaseSpider(CrawlSpider):
    colour_api = "{start_url}pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"

    def parse(self, response):
        xpath = '//ul[contains(@class, "level-3")]//a/@href'
        categories = response.xpath(xpath).extract()
        for category in categories:
            yield Request(url=category, callback=self.parse_pagination)

    def parse_pagination(self, response):
        product_urls = response.css('.product-image a ::attr(href)').extract()
        for product_url in product_urls:
            yield Request(url=product_url, callback=self.parse_product)
        infinite_scroll = response.css('.infinite-scroll-placeholder ::attr(data-grid-url)').extract_first()
        next_page = response.xpath('//a[contains(@class, "next")]/@href').extract_first()

        if next_page:
            yield Request(url=next_page, callback=self.parse_pagination)

        elif infinite_scroll:
            yield Request(url=HTMLParser().unescape(infinite_scroll), callback=self.parse_pagination)

    def parse_product(self, response):
        garment = {}
        pid = self.product_id(response)
        garment["skus"] = {}
        garment["image_urls"] = []
        product_pricing = self.product_pricing(response)
        garment["product_id"] = pid
        garment['url'] = self.product_url(response)
        garment['original_url'] = response.url
        garment["product_name"] = self.product_name(response)
        garment["product_brand"] = self.product_brand(response)
        garment["product_category"] = self.product_category(response)
        garment["skus"] = {}
        garment["requests"] = []
        garment["image_urls"] = self.image_urls(response)
        garment["requests"].extend(self.colour_requests(response, pid, garment, product_pricing))

        return self.next_request_or_garment(garment)

    def colour_requests(self, response, pid, garment, product_pricing):
        cids = self.color_ids(response, pid)
        return [Request(url=self.colour_api.format(cid=cid, pid=pid), callback=self.parse_colour, dont_filter=True,
                        meta={"garment": garment, "product_pricing": product_pricing}) for cid in cids if cid]

    def parse_colour(self, response):
        garment = response.meta["garment"]
        pricing = response.meta["product_pricing"]
        garment["skus"].update(self.skus(response, pricing))
        garment["image_urls"].extend(self.image_urls(response))
        return self.next_request_or_garment(garment)

    def skus(self, response, pricing):
        skus = {}
        common_sku = pricing
        color = response.css('li.attribute ul.Color li.selected a ::attr(title)').extract_first()

        if color:
            common_sku["color"] = color.split(':')[-1]

        for size_s in response.css('ul.size li'):
            sku = common_sku.copy()
            size = size_s.css('a ::text').extract_first() or size_s.css('span ::text').extract_first()
            if size:
                sku['size'] = size

            if size_s.css('.unselectable'):
                sku['out_of_stock'] = True

            skus['{}_{}'.format(size, color)] = sku

        return skus

    def color_ids(self, response, pid):
        color_css = 'ul.Color .swatchanchor ::attr(href),ul.color .swatchanchor ::attr(href)'
        colour_urls = response.css(color_css).extract()+[response.url]
        return [url_query_parameter(color_url, 'dwvar_{}_color'.format(pid)) for color_url in colour_urls]

    def image_urls(self, response):
        image_urls = response.css('.thumbnail-link ::attr(href)').extract()
        return [response.urljoin(image_url) for image_url in image_urls]

    def product_name(self, response):
        raw_name = self.clean(response.css('h1.product-name ::text').extract()[0:2])
        name = ' '.join(raw_name)
        return name

    def product_url(self, response):
        return response.css('link[rel="canonical"] ::attr(href)').extract_first()

    def original_url(self, response):
        return response.url

    def product_id(self, response):
        return re.findall('dwvar_(.+)_color', response.url)[0]

    def product_category(self, response):
        css = '.breadcrumb li a ::text,.breadcrumbs li a ::text'
        return self.clean(response.css(css).extract())[1:]

    def product_brand(self, response):
        xpath = '//script[contains(text(),"brand")]/text()'
        brand_text = response.xpath(xpath).extract_first()
        brand = re.findall('brand.\s?:\s?.?(.*?).,', " ".join(brand_text.split()))
        if brand:
            return brand[0].replace('"', '')

    def product_pricing(self, response):
        css = "div.product-price span ::text"
        actual_price = self.clean(response.css(css).extract())[0]
        previous_price = self.clean(response.css('span.price-sales ::text').extract())
        if previous_price:
            sales_price = previous_price[0]
            return {"price": actual_price, "sales_price": sales_price}

    def next_request_or_garment(self, garment):
        if garment['requests']:
            return garment['requests'].pop()
        del garment["requests"]

        return garment

    def clean(self, response):
        if isinstance(response, list):
            cleaned_list = [value.strip() for value in response]
            return [item for item in cleaned_list if item]
        return response.strip()