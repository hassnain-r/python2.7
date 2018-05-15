import re
import json

from scrapy.spiders import Request

from .base import DemandwareBaseSpider


class AvenueSpider(DemandwareBaseSpider):
    allowed_domains = ["www.avenue.com"]
    start_urls = ['https://www.avenue.com/']

    rotate_user_agent = True
    colour_api = "https://www.avenue.com/en_US/product-variation?" \
                 "pid={pid}&dwvar_{pid}_color={cid}&Quantity=1&format=ajax"

    name = "big_avenue"
    country_code_api = "https://www.avenue.com/on/demandware.store/Sites-Avenue-Site/en_US/51Integration-SetCountry?"

    custom_css = {
        "name_css": "h1.product-name span ::text",
        "sale_price_css": '//div[contains(@class, "sales")]//ins/text()',
        "p_price_xpath": '//script[contains(text(),"data_ave")]/text()',
    }

    def parse_homepage(self, response):
        raw_constant = ''.join(response.headers.getlist('Set-Cookie'))
        currency_constant = re.findall('\d+\.?\d+', raw_constant)[0]
        yield Request(url=self.start_urls[0], meta={"currency_constant": currency_constant},
                      callback=self.parse_categories)

    def skus(self, response, garment):
        skus = {}
        color = self.clean(response.css(self.css.colour_text_css).extract())[0]
        out_of_stock = response.css(self.css.stock_availability_css)
        raw_size = response.css(self.css.size_text_css).extract_first()
        price = self.clean(response.xpath(self.css.sale_price_css).extract_first())
        p_price = self.clean(response.xpath(self.css.p_price_xpath).extract_first())
        price = float(price)
        currency_constant = float(garment["currency_constant"])
        sku = {
            "size": self.clean(raw_size),
            "colour": color,
            "price": round(price * currency_constant, 2),
        }

        if p_price:
            prev_price = float(p_price)

        else:
            prev_price = float(garment["previous_price"])

        sku["previous_price"] = round(prev_price * currency_constant, 2)

        if response.css(self.css.variant_url_css):
            variant = response.css(self.css.variant_text_css).extract_first()
            sku["size"] = "{}/{}".format(sku["size"], variant)

        if out_of_stock:
            sku["out_of_stock"] = True

        skus["{}_{}".format(color, sku["size"])] = sku

        return skus

    def product_description(self, response):
        raw_description = response.css('.copy-ctn-sec ::text').extract()
        return [' '.join(raw_description).split('var masterID')[0].strip()]

    def raw_details(self, response):
        raw_json = response.xpath(self.css.p_price_xpath).extract_first()
        raw_data = " ".join(raw_json.split())
        raw_data = re.findall('data_ave = (.+});', raw_data)[0]
        return json.loads(raw_data)["product_sales_price_ave"]
