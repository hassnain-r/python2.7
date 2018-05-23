# -*- coding: utf-8 -*-

import re
import json
import copy
import urlparse

from copy import deepcopy
from scrapy.selector import Selector
from scrapy import Request, FormRequest

from scrapyproduct.spiderlib import SSBaseSpider
from scrapyproduct.items import ProductItem, SizeItem


class LinigSpider(SSBaseSpider):
    name = "lining_spider"
    long_name = "lining"
    base_url = "https://store.lining.com/"
    version = '1.0.0'
    seen_skus = set()
    max_stock_level = 10000
    details_api = "https://store.lining.com/ajax/goods_details.html"

    def start_requests(self):
        meta = {
            "country_code": "cn",
            "currency": "CNY",
            "language_code": "zh",
        }
        yield Request(url=self.base_url, meta=meta, callback=self.parse_homepage)

    def parse_homepage(self, response):
        meta = copy.deepcopy(response.meta)
        categories_json = response.xpath('//script[contains(text(),"bannerHtml")]/text()').extract_first()
        cat_url = re.findall('url: "(.*?)"', categories_json)[0]
        yield Request(url=cat_url, meta=meta, callback=self.parse_categories)

    def parse_categories(self, response):
        meta = copy.deepcopy(response.meta)
        categories_details = response.text
        raw_categories = json.loads(categories_details)

        for category in raw_categories["data"]["banner"]:
            level0 = category["title"]
            mid_links = category["mid"]
            if mid_links:
                for sub_cat in mid_links:
                    level1 = sub_cat["title"]

                    for level2_text in sub_cat["small"]:
                        level2 = level2_text["title"]
                        level2_url = level2_text["link"]
                        categories = [level0, level1, level2]
                        meta["categories"] = categories
                        yield Request(url=response.urljoin(level2_url), meta=meta, callback=self.parse_product)

            else:
                sub_cat_html = category["htmlShow"]
                cat_sel = Selector(text=sub_cat_html)
                level1_text = cat_sel.css('a.fontG')

                for level1_sel in level1_text:
                    level1 = level1_sel.css('::text').extract_first()
                    level1_url = level1_sel.css('::attr(href)').extract_first()
                    categories = [level0, level1]
                    meta["categories"] = categories
                    yield Request(url=response.urljoin(level1_url), meta=meta, callback=self.parse_product)

    def parse_product(self, response):
        product_details = response.css('div.tempdata')
        for product_sel in product_details:
            base_sku = product_sel.css('::attr(sku)').extract_first()
            url = product_sel.css('::attr(goodslink)').extract_first()

            if not base_sku and url:
                continue

            item = ProductItem(
                url=url,
                referer_url=response.url,
                base_sku=base_sku,
                currency=response.meta['currency'],
                language_code=response.meta['language_code'],
                country_code=response.meta['country_code'],
                category_names=response.meta['categories'],
                brand=self.long_name,
            )

            if item.get('base_sku') not in self.seen_skus:
                self.seen_skus.add(item.get('base_sku'))

                yield Request(item['url'], meta={"item": item}, callback=self.parse_detail)

        if response.meta.get("pagination"):
            return

        product_urls = response.css('div ::attr(goodslink)').extract()
        if not product_urls:
            return

        pages_content = response.css('span.paging span ::text').extract()
        if pages_content:
            total_pages = re.findall('(\d+)', pages_content[-1])[0]

            for page in xrange(2, int(total_pages) + 1):
                updated_url = re.sub('desc,(\d*)', "desc," + str(page), response.url)

                yield Request(url=updated_url, meta=response.meta, callback=self.parse_product)

    def parse_detail(self, response):
        item = response.meta["item"]
        item["title"] = self.extract_title(response)
        item["description_text"] = self.extract_desc(response)
        item["image_urls"] = self.extract_images(response)
        colours_sel = response.css('.extrclass_top_bg ul#thumblist li a')

        for url_sel in colours_sel:
            color_item = deepcopy(item)
            color_name = url_sel.css('::attr(title)').extract_first()
            color_url = url_sel.css('::attr(href)').extract_first()
            color_code = re.findall('goods-(\d+)', color_url)[0]
            color_item['color_name'] = color_name
            color_item['color_code'] = color_code
            color_item['identifier'] = color_code
            meta = {'item': color_item}

            yield Request(url=urlparse.urljoin(self.base_url, color_url), callback=self.parse_color, meta=meta)

    def parse_color(self, response):
        item = response.meta['item']
        raw_json = response.xpath('//script[contains(text(),"sizeStr")]/text()').extract_first()
        item["brand"] = "lining"

        form_data = {
            "postID": re.findall("postID: '(.*?)'", raw_json)[0],
            "sizeStr": re.findall("sizeStr: '(.*?)'", raw_json)[0],
            "asynchStr": re.findall("goods_str: '(.*?)'", raw_json)[0],
            "product_mainID": re.findall("mainID: '(.*?)'", raw_json)[0],
            "flg": "1",
            'page_button': "0",
            "bargainTime": "0",
        }

        yield FormRequest(url=self.details_api, formdata=form_data, meta={"item": item},
                          callback=self.parse_detail_json)

    def parse_detail_json(self, response):
        item = response.meta["item"]
        detail_json = json.loads(response.text)
        item['old_price_text'] = detail_json['data']['marketPrice']
        item['new_price_text'] = detail_json['data']['price']
        size_infos = list()

        for size in detail_json["data"]["goodsData"]:
            size_name = size["spec"].split(' ')[1] or "One Size"
            size_id = size["postID"]
            stock = int(size["useFlg"])

            size_item = SizeItem(
                size_name=size_name,
                size_identifier=size_id,
                stock=stock
            )

            size_infos.append(size_item)
            item['size_infos'] = size_infos

            yield item

    def extract_desc(self, response):
        description = response.css('pre.PD_desc span ::text').extract()
        desc_sel = response.css('#p_spec li')

        for sel in desc_sel:
            key = sel.css("span.t ::text").extract_first()
            value = sel.css("span.v ::text").extract()[0]
            description.append(u"{key}:{value}".format(key=key, value=value))
        
        return description

    def extract_title(self, response):
        return response.css('h1#product_name ::text').extract_first()

    def extract_images(self, response):
        return response.css("ul#thumblist img ::attr(big)").extract()

