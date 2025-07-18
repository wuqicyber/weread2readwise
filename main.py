# !/usr/bin/env Python3
# -*- coding: utf-8 -*-
# @Author   : eleanor.zhu
# @FILE     : main.py
# @Time     : 2025/7/18 14:06
# @Software : PyCharm

import argparse
import hashlib
# 标准库
import logging
import os
import re
import time
# 时间与加密
from datetime import datetime
from http.cookies import SimpleCookie

import pytz
# 第三方库
import requests
from requests.utils import cookiejar_from_dict
from retrying import retry

WEREAD_URL = "https://weread.qq.com/"
WEREAD_NOTEBOOKS_URL = "https://weread.qq.com/api/user/notebook"
WEREAD_BOOKMARKLIST_URL = "https://weread.qq.com/web/book/bookmarklist"
WEREAD_CHAPTER_INFO = "https://i.weread.qq.com/web/book/chapterInfos"
WEREAD_READ_INFO_URL = "https://weread.qq.com/web/book/readinfo"
WEREAD_REVIEW_LIST_URL = "https://weread.qq.com/web/review/list"
WEREAD_BOOK_INFO = "https://weread.qq.com/web/book/info"

# --------------------------------------------------
# 日志配置
# --------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# 预创建全局 Session，方便在装饰器及工具函数中复用
session = requests.Session()


# --------------------------------------------------
# Retry & Cookie 刷新机制
# --------------------------------------------------

def refresh_token(exception):
    """在请求异常时尝试刷新 cookie，并告知 retrying 是否继续重试。"""
    logger.warning("请求异常，尝试刷新 WeRead cookie。异常信息: %s", exception)
    try:
        session.get(WEREAD_URL)
    except Exception as e:
        logger.error("刷新 cookie 失败: %s", e)
    # 返回 True 代表继续重试
    return True


def parse_cookie_string(cookie_string):
    cookie = SimpleCookie()
    cookie.load(cookie_string)
    cookies_dict = {}
    cookiejar = None
    for key, morsel in cookie.items():
        cookies_dict[key] = morsel.value
        cookiejar = cookiejar_from_dict(
            cookies_dict, cookiejar=None, overwrite=True
        )
    return cookiejar


# -----------------------------------------------------------------------------
# WeRead 相关接口（加上重试机制）
# -----------------------------------------------------------------------------

@retry(stop_max_attempt_number=3, wait_fixed=5000, retry_on_exception=refresh_token)
def get_bookmark_list(bookId):
    """获取我的划线"""
    session.get(WEREAD_URL)
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOKMARKLIST_URL, params=params)
    if r.ok:
        updated = r.json().get("updated")
        updated = sorted(updated, key=lambda x: (
            x.get("chapterUid", 1), int(x.get("range").split("-")[0])))
        return r.json()["updated"]
    return None


@retry(stop_max_attempt_number=3, wait_fixed=5000, retry_on_exception=refresh_token)
def get_read_info(bookId):
    session.get(WEREAD_URL)
    params = dict(bookId=bookId, readingDetail=1,
                  readingBookIndex=1, finishedDate=1)
    r = session.get(WEREAD_READ_INFO_URL, params=params)
    if r.ok:
        return r.json()
    return None


@retry(stop_max_attempt_number=3, wait_fixed=5000, retry_on_exception=refresh_token)
def get_bookinfo(bookId):
    """获取书的详情"""
    session.get(WEREAD_URL)
    params = dict(bookId=bookId)
    r = session.get(WEREAD_BOOK_INFO, params=params)
    isbn = ""
    if r.ok:
        data = r.json()
        isbn = data["isbn"]
        newRating = data["newRating"] / 1000
    return (isbn, newRating)


@retry(stop_max_attempt_number=3, wait_fixed=5000, retry_on_exception=refresh_token)
def get_review_list(bookId):
    """获取笔记"""
    session.get(WEREAD_URL)
    params = dict(bookId=bookId, listType=11, mine=1, syncKey=0)
    r = session.get(WEREAD_REVIEW_LIST_URL, params=params)
    reviews = r.json().get("reviews")
    summary = list(filter(lambda x: x.get("review").get("type") == 4, reviews))
    reviews = list(filter(lambda x: x.get("review").get("type") == 1, reviews))
    reviews = list(map(lambda x: x.get("review"), reviews))
    reviews = list(map(lambda x: {**x, "note": x.pop("content")}, reviews))
    reviews = list(map(lambda x: {**x, "markText": x.get("abstract", x.get('note'))}, reviews))
    return summary, reviews


def get_table_of_contents():
    """获取目录"""
    return {
        "type": "table_of_contents",
        "table_of_contents": {
            "color": "default"
        }
    }


def get_heading(level, content):
    if level == 1:
        heading = "heading_1"
    elif level == 2:
        heading = "heading_2"
    else:
        heading = "heading_3"
    return {
        "type": heading,
        heading: {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content,
                }
            }],
            "color": "default",
            "is_toggleable": False
        }
    }


def get_quote(content):
    return {
        "type": "quote",
        "quote": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content
                },
            }],
            "color": "default"
        }
    }


def get_callout(content, style, colorStyle, reviewId):
    # 根据不同的划线样式设置不同的emoji 直线type=0 背景颜色是1 波浪线是2
    emoji = "🌟"
    if style == 0:
        emoji = "💡"
    elif style == 1:
        emoji = "⭐"
    # 如果reviewId不是空说明是笔记
    if reviewId != None:
        emoji = "✍️"
    color = "default"
    # 根据划线颜色设置文字的颜色
    if colorStyle == 1:
        color = "red"
    elif colorStyle == 2:
        color = "purple"
    elif colorStyle == 3:
        color = "blue"
    elif colorStyle == 4:
        color = "green"
    elif colorStyle == 5:
        color = "yellow"
    return {
        "type": "callout",
        "callout": {
            "rich_text": [{
                "type": "text",
                "text": {
                    "content": content,
                }
            }],
            "icon": {
                "emoji": emoji
            },
            "color": color
        }
    }


def get_notebooklist():
    """获取笔记本列表"""
    r = session.get(WEREAD_NOTEBOOKS_URL)
    if r.ok:
        data = r.json()
        books = data.get("books")
        books.sort(key=lambda x: x["sort"])
        return books
    else:
        print(r.text)
    return None


def transform_id(book_id):
    id_length = len(book_id)

    if re.match("^\d*$", book_id):
        ary = []
        for i in range(0, id_length, 9):
            ary.append(format(int(book_id[i:min(i + 9, id_length)]), 'x'))
        return '3', ary

    result = ''
    for i in range(id_length):
        result += format(ord(book_id[i]), 'x')
    return '4', [result]


def calculate_book_str_id(book_id):
    md5 = hashlib.md5()
    md5.update(book_id.encode('utf-8'))
    digest = md5.hexdigest()
    result = digest[0:3]
    code, transformed_ids = transform_id(book_id)
    result += code + '2' + digest[-2:]

    for i in range(len(transformed_ids)):
        hex_length_str = format(len(transformed_ids[i]), 'x')
        if len(hex_length_str) == 1:
            hex_length_str = '0' + hex_length_str

        result += hex_length_str + transformed_ids[i]

        if i < len(transformed_ids) - 1:
            result += 'g'

    if len(result) < 20:
        result += digest[0:20 - len(result)]

    md5 = hashlib.md5()
    md5.update(result.encode('utf-8'))
    result += md5.hexdigest()[0:3]
    return result


def ctime2utc(ctime):
    # 将 Unix 时间戳转换为 datetime 对象
    dt_object = datetime.fromtimestamp(ctime)

    # 设置时区为东八区
    timezone = pytz.timezone('Asia/Shanghai')
    dt_object = timezone.localize(dt_object)

    # 将 datetime 对象转换为 ISO 8601 格式的字符串
    iso_format = dt_object.isoformat()

    return iso_format  # 输出：2016-09-28T15:50:12+08:00


def try_get_cloud_cookie(url, id, password):
    if url.endswith("/"):
        url = url[:-1]
    req_url = f"{url}/get/{id}"
    data = {"password": password}
    result = None
    response = requests.post(req_url, data=data)
    if response.status_code == 200:
        data = response.json()
        cookie_data = data.get("cookie_data")
        if cookie_data and "weread.qq.com" in cookie_data:
            cookies = cookie_data["weread.qq.com"]
            cookie_str = "; ".join(
                [f"{cookie['name']}={cookie['value']}" for cookie in cookies]
            )
            result = cookie_str
    return result


def get_cookie():
    url = os.getenv("CC_URL")
    if not url:
        url = "https://cookiecloud.malinkang.com/"
    id = os.getenv("CC_ID")
    password = os.getenv("CC_PASSWORD")
    cookie = os.getenv("WEREAD_COOKIE")
    if url and id and password:
        cookie = try_get_cloud_cookie(url, id, password)
    if not cookie or not cookie.strip():
        raise Exception("没有找到cookie，请按照文档填写cookie")
    return cookie


# -----------------------------------------------------------------------------
# CLI 入口
# -----------------------------------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="将微信读书划线/笔记同步到 Readwise",
    )
    parser.add_argument(
        "-c",
        "--weread-cookie",
        dest="weread_cookie",
        help="WeRead 的 Cookie。如果不提供，则尝试从环境变量中读取或通过 CookieCloud 获取。",
    )
    parser.add_argument(
        "-t",
        "--readwise-token",
        dest="readwise_token",
        help="Readwise API Token。可以通过该参数或环境变量 READWISE_TOKEN 指定。",
    )

    options = parser.parse_args()

    # 处理 weread cookie
    if options.weread_cookie:
        weread_cookie = options.weread_cookie
    else:
        weread_cookie = get_cookie()

    # 处理 readwise token
    readwise_token = options.readwise_token or os.getenv("READWISE_TOKEN")
    if not readwise_token:
        parser.error("必须提供 Readwise Token，可以通过 --readwise-token 或环境变量 READWISE_TOKEN 指定")

    # 更新全局 Session
    session.cookies = parse_cookie_string(weread_cookie)
    session.get(WEREAD_URL)

    books = get_notebooklist()

    # 提取书籍和笔记的数量
    querystring = {
        'page_size': 1000,
        "category": "books",
        "source": "weread_app",

    }

    response = requests.get(
        url="https://readwise.io/api/v2/books/",
        headers={"Authorization": f"Token {readwise_token}"},
        params=querystring
    )

    data = response.json()
    readwise_book_num = data['count']
    readwise_book = {book['title']: book['num_highlights'] for book in data['results']}

    # 开始导入
    if (books != None):
        for book in books[:]:
            # 无笔记跳过
            if book.get("noteCount", 0) + book.get("reviewCount", 0) == 0:
                continue
            sort = book["sort"]
            book = book.get("book")
            title = book.get("title").replace('/', '').replace(':', '')
            cover = book.get("cover")
            bookId = book.get("bookId")
            author = book.get("author")

            bookmark_list = get_bookmark_list(bookId)
            summary, reviews = get_review_list(bookId)
            bookmark_list.extend(reviews)
            # print(title,bookId)

            if title in readwise_book and len(bookmark_list) == readwise_book[title]:
                print("跳过", title, bookId)
                continue
            else:
                annotations = []

            bookmark_list = sorted(bookmark_list, key=lambda x: (
                x.get("chapterUid", 1), 0 if (x.get("range", "") == "" or x.get("range").split("-")[0] == "") else int(
                    x.get("range").split("-")[0])))

            for bookmark in bookmark_list:
                time.sleep(0.3)

                params = {
                    "text": bookmark['markText'],
                    "title": title,
                    "author": author,
                    "source_type": "weread_app",
                    "category": "books",
                    # "location": bookmark['range'],
                    # "location_type": ,
                    'image_url': cover,
                    'source_url': f"https://weread.qq.com/web/reader/{calculate_book_str_id(bookId)}",
                    "highlighted_at": ctime2utc(bookmark['createTime']),  # "2020-07-14T20:11:24+00:00",

                }
                if 'note' in bookmark:
                    params['note'] = bookmark.get('note')
                    reviewId = bookmark.get('reviewId')
                    params['highlight_url'] = f'https://weread.qq.com/review-detail?reviewid={reviewId}&type=1'

                annotations.append(params)

            resp = requests.post(
                url="https://readwise.io/api/v2/highlights/",
                headers={"Authorization": f"Token {readwise_token}"},
                # headers={"Authorization": f"Token {readwise_token}"},
                json={
                    "highlights": annotations
                }
            )
            print(resp)
            time.sleep(8)
