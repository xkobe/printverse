#!/usr/bin/env python3
"""
PrintVerse 热销款采集脚本
通过Apify API采集Temu/Shein/Etsy三平台POD热销商品
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# 配置
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
IMAGES_DIR = DATA_DIR / "images"

# Apify Actors
ACTORS = {
    "temu": "amit123~temu-products-scraper",
    "shein": "shahidirfan~shein-product-scraper",
    "etsy": "yumitori~etsy-listings-scraper",
}

# POD热门关键词
POD_KEYWORDS = [
    "graphic tee",
    "vintage t shirt design",
    "funny slogan shirt",
    "retro animal print",
    "floral sublimation design",
    "quote shirt aesthetic",
    "boho minimalist tee",
    "western country shirt",
    "halloween spooky design",
    "christmas holiday tee",
]

# 每平台采集量
LIMITS = {
    "temu": 20,
    "shein": 5,
    "etsy": 5,
}

# POD相关关键词过滤
POD_FILTER = ["shirt", "tee", "t-shirt", "tshirt", "hoodie", "sweatshirt", "print", "graphic", "sublimation", "png", "design"]


def ensure_dirs():
    for d in [RAW_DIR, IMAGES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def apify_request(method, path, data=None):
    """发送Apify API请求"""
    url = f"https://api.apify.com/v2{path}?token={APIFY_TOKEN}"
    headers = {"Content-Type": "application/json"}
    if method == "POST":
        resp = requests.post(url, json=data, headers=headers, timeout=30)
    else:
        resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def run_actor(platform, keyword, max_items):
    """启动Apify Actor并等待完成"""
    actor_id = ACTORS[platform]

    # 构建输入
    if platform == "temu":
        run_input = {
            "searchQueries": [keyword],
            "maxItems": max_items,
        }
    elif platform == "shein":
        search_url = f"https://us.shein.com/pdsearch/{keyword.replace(' ', '%20')}/"
        run_input = {
            "startUrl": search_url,
        }
    elif platform == "etsy":
        run_input = {
            "queries": [keyword],
            "maxItems": max_items,
        }
    else:
        return []

    print(f"  启动 {platform} 采集: keyword='{keyword}', max={max_items}")

    # 启动运行
    result = apify_request("POST", f"/acts/{actor_id}/runs", run_input)
    run_id = result["data"]["id"]
    print(f"  Run ID: {run_id}")

    # 等待完成（最多5分钟）
    for i in range(60):
        time.sleep(5)
        status = apify_request("GET", f"/actor-runs/{run_id}")
        state = status["data"]["status"]
        if state in ["SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"]:
            print(f"  状态: {state} (耗时 {status['data'].get('stats',{}).get('durationMillis',0)/1000:.1f}s)")
            break
        if i % 6 == 0:
            print(f"  等待中... ({state})")
    else:
        print(f"  超时，跳过")
        return []

    if state != "SUCCEEDED":
        print(f"  运行失败: {state}")
        return []

    # 获取数据集
    dataset_id = status["data"]["defaultDatasetId"]
    items = apify_request("GET", f"/datasets/{dataset_id}/items")
    print(f"  获取到 {len(items)} 条数据")
    return items


def is_pod_product(title):
    """判断是否为POD相关商品"""
    title_lower = title.lower()
    return any(kw in title_lower for kw in POD_FILTER)


def normalize_item(platform, item, keyword):
    """标准化商品数据"""
    if platform == "temu":
        return {
            "platform": "temu",
            "title": item.get("title", ""),
            "price": item.get("price_info", {}).get("price", ""),
            "image": item.get("image", {}).get("url", ""),
            "url": item.get("link_url", ""),
            "sales_tip": item.get("sales_tip", ""),
            "comment": item.get("comment", ""),
            "keyword": keyword,
        }
    elif platform == "shein":
        return {
            "platform": "shein",
            "title": item.get("goods_name", ""),
            "price": item.get("salePrice", {}).get("amountWithSymbol", ""),
            "image": item.get("goods_img", ""),
            "url": item.get("链接", ""),
            "sales_tip": "",
            "comment": "",
            "keyword": keyword,
        }
    elif platform == "etsy":
        return {
            "platform": "etsy",
            "title": item.get("title", ""),
            "price": item.get("price", ""),
            "image": item.get("image", ""),
            "url": item.get("listingUrl", ""),
            "sales_tip": "",
            "comment": "",
            "keyword": keyword,
        }
    return {}


def download_image(url, save_path):
    """下载商品图片"""
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    图片下载失败: {e}")
        return False


def main():
    ensure_dirs()

    if not APIFY_TOKEN:
        print("错误: 未设置 APIFY_TOKEN 环境变量")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== PrintVerse 采集任务 {today} ===")
    print(f"Token: {APIFY_TOKEN[:10]}...")

    all_products = []

    for platform in ["temu", "shein", "etsy"]:
        limit = LIMITS[platform]
        # 每个平台用前2个关键词采集，分摊数量
        keywords = POD_KEYWORDS[:2]
        per_kw = max(1, limit // len(keywords))

        print(f"\n--- {platform.upper()} (目标 {limit} 条) ---")

        for keyword in keywords:
            try:
                items = run_actor(platform, keyword, per_kw)
                for item in items:
                    normalized = normalize_item(platform, item, keyword)
                    if normalized.get("title") and is_pod_product(normalized["title"]):
                        all_products.append(normalized)
            except Exception as e:
                print(f"  采集异常: {e}")
                continue

        # 保存原始数据
        raw_file = RAW_DIR / f"{platform}_{today}.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump([p for p in all_products if p["platform"] == platform], f, ensure_ascii=False, indent=2)
        print(f"  已保存原始数据: {raw_file}")

    # 去重（按标题）
    seen_titles = set()
    unique_products = []
    for p in all_products:
        if p["title"] not in seen_titles:
            seen_titles.add(p["title"])
            unique_products.append(p)

    print(f"\n=== 采集汇总 ===")
    print(f"总采集: {len(all_products)} 条")
    print(f"去重后: {len(unique_products)} 条")
    for platform in ["temu", "shein", "etsy"]:
        count = len([p for p in unique_products if p["platform"] == platform])
        print(f"  {platform}: {count} 条")

    # 下载图片
    print(f"\n--- 下载商品图片 ---")
    for i, product in enumerate(unique_products):
        if product.get("image"):
            img_ext = ".jpg"
            if ".png" in product["image"].lower():
                img_ext = ".png"
            img_name = f"{product['platform']}_{i:03d}{img_ext}"
            img_path = IMAGES_DIR / img_name
            if not img_path.exists():
                print(f"  [{i+1}/{len(unique_products)}] 下载: {product['title'][:40]}...")
                if download_image(product["image"], img_path):
                    product["local_image"] = f"data/images/{img_name}"
            else:
                product["local_image"] = f"data/images/{img_name}"

    # 保存汇总数据
    products_file = DATA_DIR / "products.json"
    output = {
        "updated_at": datetime.now().isoformat(),
        "total": len(unique_products),
        "products": unique_products,
    }
    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n汇总数据已保存: {products_file}")

    # 输出统计供GitHub Actions读取
    print(f"\n::set-output name=total::{len(unique_products)}")
    print(f"::set-output name=temu::{len([p for p in unique_products if p['platform']=='temu'])}")
    print(f"::set-output name=shein::{len([p for p in unique_products if p['platform']=='shein'])}")
    print(f"::set-output name=etsy::{len([p for p in unique_products if p['platform']=='etsy'])}")

    print("\n=== 采集完成 ===")


if __name__ == "__main__":
    main()
