import re
import json

from scrapy.spiders import Request, CrawlSpider
from w3lib.url import add_or_replace_parameter, url_query_parameter


class AvenueSpider(CrawlSpider):
    name = "avenue_spider"
    deny_url = ["/en_US/plus-size-clothing/tops-knit-tops/#prefn1=size&prefv1=30%7C32&hcgid=tops-knit-tops"]
    GBP_currency_constant = 0.8586946500
    color_ids_regex = 'swatch/\d+.(.+)-SW.jpg'
    color_ids_css = '[class="swatches Color clearfix"] a ::attr(style)'
    color_url_api = "https://www.avenue.com/en_US/product-variation?"
    images_api = 'https://www.avenue.com/dw/image/v2/AAMJ_PRD/on/demandware.static/-/Sites-avenue-master-catalog/' \
                 'default/images/large/'

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"
                      " Chrome/64.0.3282.167 Safari/537.36",
        "FiftyOne_Akamai": "GB|GBP|0.8586946500|2",

    }

    cookies = {
        "FiftyOne_Akamai": "GB|GBP|0.8586946500|2",
        "SL_VIS_97134392": "Y2lkPWNwLXRvYy01NzE0JnNsdD0xNTI0MTU0MjQyLjY1NSZ1aWQ9NCZoYWc9NTcxNCZzdmM9MTkzMiZ2"
                               "aWQ9MUUwMkU5QkYtQjNENy0wMDAxLTkxQzMtMTFFQzFBRjAxNDJGJnJldD0xJnh0Yz0wJnhsdD0mY2"
                               "k9JmV4cD1XZWQlMkMlMjAxOCUyMEp1bCUyMDIwMTglMjAxNiUzQTEwJTNBNDIlMjBHTVQmZG9tPS5h"
                               "dmVudWUuY29tJnJlZj0mZW50cnk9aHR0cHMlM0ElMkYlMkZ3d3cuYXZlbnVlLmNvbSUyRndvbWVucy"
                               "UyRmNsb3RoaW5nJTJGaW5kZXg0Lmh0bWw",
    }

    def start_requests(self):
        url = "https://www.avenue.com/"
        yield Request(url, headers=self.headers, cookies=self.cookies, callback=self.parse_categories)

    def parse_categories(self, response):
        sub_categories = response.css("ul.level-3 li a ::attr(href)").extract()
        for sub_category in sub_categories:

            if sub_category in self.deny_url:
                continue
            yield Request(url=sub_category, headers=self.headers, cookies=self.cookies,
                          callback=self.parse_pagination)

    def parse_pagination(self, response):
        product_urls = response.css('a[class="thumb-link"] ::attr(href)').extract()
        for product_url in product_urls:
            yield Request(url=product_url, headers=self.headers, cookies=self.cookies,
                          callback=self.parse_product)

        raw_url = response.css('.infinite-scroll-placeholder ::attr(data-grid-url)').extract_first()
        if raw_url:
            next_page_url = raw_url.replace('amp;', '')
            yield Request(url=next_page_url, headers=self.headers, cookies=self.cookies,
                          callback=self.parse_categories)

    def parse_product(self, response):
        print response.text
        raw_details = self.raw_details(response)
        garment = {}

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
        garment["requests"] += self.colour_requests(response, pid, garment)

        return self.next_request_or_garment(garment)

    def colour_requests(self, response, pid, garment):
        color_ids = self.color_ids(response)
        color_id_key = "{}_{}_{}".format("dwvar", pid, "color")

        return [Request(url="{}{}={}&pid={}&format=ajax".format(self.color_url_api, color_id_key, color_id, pid),
                        dont_filter=True, meta={"garment": garment}, callback=self.parse_colors)
                for color_id in color_ids]

    def parse_colors(self, response):
        garment = response.meta["garment"]
        garment['requests'] += self.size_requests(response, garment)

        return self.next_request_or_garment(garment)

    def size_requests(self, response, garment):
        css = 'ul[class="swatches size clearfix"] a.swatchanchor ::attr(href)'
        available_sizes = response.css(css).extract()

        return [Request(url="{}&format=ajax".format(size_url), dont_filter=True, meta={"garment": garment},
                        callback=self.parse_sizes) for size_url in available_sizes]

    def parse_sizes(self, response):
        garment = response.meta["garment"]
        if self.variant_urls(response):
            garment["requests"] += self.variant_requests(response, garment)

            return self.next_request_or_garment(garment)

        else:
            garment["skus"].update(self.skus(response, garment))
            return self.next_request_or_garment(garment)

    def variant_requests(self, response, garment):
        variant_urls = self.variant_urls(response)
        return [Request(url="{}&format=ajax".format(variant_url), dont_filter=True, meta={"garment": garment},
                        callback=self.parse_variants) for variant_url in variant_urls]

    def parse_variants(self, response):
        garment = response.meta["garment"]
        garment["skus"].update(self.skus(response, garment))

        return self.next_request_or_garment(garment)

    def product_pricing(self, response, garment):
        size_css = 'ul[class="swatches size clearfix"] li.selected-value ::text'
        size = response.css(size_css).extract_first().strip()
        raw_color = response.css('ul[class="swatches Color clearfix"] li.selected ::text').extract()
        color = ''.join(raw_color).strip()
        price, previous_price, currency = float(garment["price"]), float(garment["previous_price"]), garment["currency"]

        sku = {
            "size": size,
            "colour": color,
            "price": round(price * self.GBP_currency_constant, 2),
            "currency": currency,
            "previous_price": round(previous_price * self.GBP_currency_constant, 2)
            }

        return sku
    
    def skus(self, response, garment):
        skus = {}
        sku = self.product_pricing(response, garment)

        if self.variant_urls(response):
            raw_variant = response.css('ul[class="swatches range clearfix"] li.selected ::text').extract()
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
        return response.css('ul[class="swatches range clearfix"] a.swatchanchor ::attr(href)').extract()

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
