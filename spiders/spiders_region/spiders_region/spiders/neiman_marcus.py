import json
import re
import base64

from scrapy.spiders import CrawlSpider
from scrapy import FormRequest, Request
from scrapy.selector import Selector


class NeimanMarcusSpider(CrawlSpider):
    name = "neiamn_marcus"
    country_api = "https://www.neimanmarcus.com/dt/api/profileCountryData"
    colour_size_api = "https://www.neimanmarcus.com/en-gb/product.service"
    image_api = "https://neimanmarcus.scene7.com/is/image/NeimanMarcus/"
    pagination_api = "https://www.neimanmarcus.com/en-gb/category.service"
    start_urls = ["https://www.neimanmarcus.com/"]

    # def __init__(self, country="", currency="", **kwargs):
    #     super(NeimanMarcusSpider, self).__init__(**kwargs)
    #     self.start_urls = [
    #         'https://www.neimanmarcus.com/',
    #     ]
    #
    #     self.country = "%s" % country
    #     self.currency = "%s" % currency

    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
                      ' Chrome/64.0.3282.167 Safari/537.36',
        'DOWNLOAD_DELAY': 2.5
    }

    gender_map = [
        ("Men", "men"),
        ("Women", "women"),
        ("Kids", "Unisex-kids")
    ]
    #
    # def parse(self, response):
    #     for country, currency in zip(self.country.split(','), self.currency.split(',')):
    #         form_data = {
    #             "country": country,
    #             "currency": currency,
    #             }
    #         yield FormRequest(url=self.country_api, formdata=form_data, callback=self.parse_homepage)

    def parse(self, response):
        raw_categories = response.css('#state ::text').extract_first()
        categories = re.findall('url":"(.*?)"', raw_categories)
        for category in categories:
            yield Request(url=response.urljoin(category), callback=self.parse_categories)

    def parse_categories(self, response):
        max_page_num = response.css('li.pageOffset ::text').extract()
        if max_page_num:
            request_data = self.request_data(response)
            for pageoffset in range(1, int(max_page_num[-2]) + 1):
                request_data["pageOffset"] = pageoffset
                encoded_data = base64.b64encode(json.dumps({'GenericSearchReq': request_data}))
                data = '$b64$' + re.sub('\$+', '=', encoded_data)
                form_data = {
                    "data": data,
                    "service": "getCategoryGrid"
                }
                yield FormRequest(url=self.pagination_api, formdata=form_data, callback=self.parse_pagination)

    def parse_pagination(self, response):
        product_urls_text = json.loads(response.text)["GenericSearchResp"]["productResults"]
        product_sel = Selector(text=product_urls_text)
        product_urls = product_sel.css('a#colorSwatch ::attr(href)').extract()
        for product_url in product_urls:
            yield Request(url=response.urljoin(product_url), callback=self.parse_product)

    def request_data(self, response):
        req_filters = {'StoreLocationFilterReq': [{'allStoresInput': 'false'}]}
        page_size = response.css('dd.SEEME ::attr(data)').extract_first()
        raw_path = response.xpath('//script[contains(text(),"DefinitionPath")]/text()').extract_first()
        path = re.findall("Path = '(.+)';", raw_path)[0]
        raw_details = response.css('#rootcatnav ::attr(href)').extract_first()
        category_id = raw_details.split('_')[-1]
        silo = raw_details.split('?')[1]

        sort = response.css('input#sort ::attr(value)').extract_first()

        request_data = {
            "pageSize": page_size,
            "categoryId": category_id,
            "advancedFilterReqItems": req_filters,
            "definitionPath": path,
            "rwd": "true",
            "endecaDrivenSiloRefinements": silo,
            "sort": sort,
            "refinements": "",
        }
        return request_data

    def parse_product(self, response):
        garment = {}
        raw_product = self.raw_product(response)
        pid = raw_product["product_id"][0]
        garment["product_name"] = raw_product["product_name"][0]
        garment["product_id"] = pid
        garment["product_category"] = raw_product["bread_crumb"][1:]
        garment["url"] = self.product_url(response)
        garment["original_url"] = response.url
        garment["product_description"] = self.product_description(response)
        garment["product_brand"] = self.product_brand(response)
        garment["image_urls"] = self.image_urls(response)
        garment["product_gender"] = self.product_gender(garment)
        product_pricing = self.product_pricing(response)
        return self.colour_size_requests(pid, garment, product_pricing)

    def colour_size_requests(self, pid, garment, product_pricing):
        decoded_data = json.dumps({'ProductSizeAndColor': {'productIds': pid}})
        data = '$b64${}'.format(base64.b64encode(decoded_data))

        form_data = {
            "data": data
        }

        return FormRequest(url=self.colour_size_api, meta={"garment": garment, "product_pricing": product_pricing},
                           formdata=form_data, callback=self.parse_color_sizes)

    def parse_color_sizes(self, response):
        product_pricing = response.meta["product_pricing"]
        garment = response.meta["garment"]
        raw_json = json.loads(response.text)
        raw_skus = json.loads(raw_json['ProductSizeAndColor']['productSizeAndColorJSON'])[0]
        garment["skus"] = self.skus(raw_skus, product_pricing)
        return garment

    def skus(self, raw_skus, product_pricing):
        skus = {}
        common_sku = product_pricing

        for product_skus in raw_skus["skus"]:
            sku = common_sku. copy()
            colour = product_skus.get("color")

            if colour:
                sku["colour"] = colour.split('?')[0]
            size = product_skus.get("size")

            if size:
                sku["size"] = size

            if product_skus["status"] != "In Stock":
                sku["out_of_stock"] = True

            skus[product_skus["sku"]] = sku
        return skus

    def image_urls(self, response):
        raw_ids = response.css('li.color-picker ::attr(data-sku-img)').extract()
        color_ids = re.findall(':"(.*?)"', ' '.join(raw_ids))
        images = response.css('div[class="img-wrap"] img[itemprop="image"] ::attr(src)').extract()
        return ["{}{}?&wid=400&height=500".format(self.image_api, color_id) for color_id in color_ids] or images

    def product_url(self, response):
        return response.css('link[rel="canonical"] ::attr(href)').extract_first()

    def raw_product(self, response):
        xpath = '//script[contains(text(), "page_definition_id")]/text()'
        raw_product = response.xpath(xpath).extract_first()
        raw_product = re.findall('utag_data=(.+);', raw_product)[0]
        return json.loads(raw_product)

    def product_gender(self, garment):
        categories = '{}{}'.format(' '.join(garment["product_category"]), garment["product_name"])
        for gender_key, gender_value in self.gender_map:
            if gender_key in categories:
                return gender_value or "unisex-adults"

    def product_pricing(self, response):
        price = response.css('[itemprop="price"] ::text').extract_first().strip()
        currency = response.css('meta[itemprop="priceCurrency"] ::attr(content)').extract_first()
        previous_price = response.css('.item-price ::text').extract_first()
        return {"price": price, "previous_price": previous_price, "currency": currency}

    def product_brand(self, response):
        return response.css('span[itemprop="brand"] ::text').extract_first()

    def product_description(self, response):
        return response.css('div.productCutline li ::text').extract()
