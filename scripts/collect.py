#!/usr/bin/env python3
"""
PrintVerse 热销款采集脚本 v2
通过Apify API采集Temu/Shein/Etsy三平台POD热销商品
优化：Temu重试机制、放宽过滤、增加关键词、详细日志
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

# Apify Actors（主选+备选）
ACTORS = {
    "temu": ["amit123~temu-products-scraper", "webscraping~temu-scraper"],
    "shein": ["shahidirfan~shein-product-scraper"],
    "etsy": ["yumitori~etsy-listings-scraper"],
}

# 测试模式控制（测试期间用小数据量节省额度，正式运行时设为false）
TEST_MODE = os.environ.get("TEST_MODE", "true").lower() == "true"

# POD热门关键词（按平台优化）
if TEST_MODE:
    # 测试模式：极致省，每平台1关键词×3条，总计9条，成本约$0.001/次
    TEMU_KEYWORDS = ["graphic tee"]
    SHEIN_KEYWORDS = ["graphic t shirt"]
    ETSY_KEYWORDS = ["graphic tee png"]
    PER_KEYWORD_LIMIT = {"temu": 3, "shein": 3, "etsy": 3}
    print(f"[测试模式-极致省] Temu 1词×3, Shein 1词×3, Etsy 1词×3, 总计9条")
else:
    # 正式模式：完整数据量
    TEMU_KEYWORDS = ["graphic tee", "t shirt", "vintage t shirt", "funny shirt", "hoodie"]
    SHEIN_KEYWORDS = ["graphic t shirt", "oversized tee", "vintage shirt", "print tee", "hoodie"]
    ETSY_KEYWORDS = ["graphic tee png", "t shirt design", "sublimation design", "shirt png", "retro shirt"]
    PER_KEYWORD_LIMIT = {"temu": 8, "shein": 5, "etsy": 5}

# 放宽过滤：只要包含服装相关词就保留（不过度过滤）
POD_FILTER = [
    "shirt", "tee", "t-shirt", "tshirt", "hoodie", "sweatshirt", "top",
    "print", "graphic", "sublimation", "png", "design", "tee shirt",
    "casual", "short sleeve", "long sleeve", "crew neck", "v neck",
]


def ensure_dirs():
    for d in [RAW_DIR, IMAGES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def apify_request(method, path, data=None, timeout=30):
    """发送Apify API请求"""
    url = f"https://api.apify.com/v2{path}?token={APIFY_TOKEN}"
    headers = {"Content-Type": "application/json"}
    if method == "POST":
        resp = requests.post(url, json=data, headers=headers, timeout=timeout)
    else:
        resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def run_actor(platform, keyword, max_items, max_retries=2):
    """启动Apify Actor并等待完成，支持重试和备选actor"""
    actor_list = ACTORS[platform]

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

    for actor_idx, actor_id in enumerate(actor_list):
        for attempt in range(max_retries):
            try:
                print(f"  [Actor {actor_idx+1}/{len(actor_list)}, 尝试 {attempt+1}/{max_retries}] {platform}: keyword='{keyword}', max={max_items}")

                # 启动运行
                result = apify_request("POST", f"/acts/{actor_id}/runs", run_input)
                run_id = result["data"]["id"]
                print(f"  Run ID: {run_id} (actor: {actor_id})")

                # 等待完成（最多4分钟）
                for i in range(48):
                    time.sleep(5)
                    status = apify_request("GET", f"/actor-runs/{run_id}")
                    state = status["data"]["status"]
                    if state in ["SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"]:
                        duration = status["data"].get("stats", {}).get("durationMillis", 0) / 1000
                        print(f"  状态: {state} (耗时 {duration:.1f}s)")
                        break
                    if i % 6 == 0:
                        print(f"  等待中... ({state})")
                else:
                    print(f"  超时，跳过")
                    continue

                if state != "SUCCEEDED":
                    print(f"  运行失败: {state}")
                    if attempt < max_retries - 1:
                        print(f"  5秒后重试...")
                        time.sleep(5)
                    continue

                # 获取数据集
                dataset_id = status["data"]["defaultDatasetId"]
                items = apify_request("GET", f"/datasets/{dataset_id}/items")
                print(f"  获取到 {len(items)} 条原始数据")

                # 手动截断（部分actor不遵守maxItems参数）
                if len(items) > max_items:
                    items = items[:max_items]
                    print(f"  截断到 {max_items} 条")

                if items:
                    return items
                else:
                    print(f"  ⚠️ 数据集为空，尝试下一个actor")
                    break  # 跳出重试循环，试下一个actor

            except Exception as e:
                print(f"  采集异常: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    print(f"  5秒后重试...")
                    time.sleep(5)
                continue

    print(f"  {platform} 采集失败（已尝试所有actor）")
    return []


def is_pod_product(title):
    """判断是否为POD相关商品（放宽过滤）"""
    if not title:
        return False
    title_lower = title.lower()
    # 只要包含任意服装/印花相关词就保留
    return any(kw in title_lower for kw in POD_FILTER)


def normalize_item(platform, item, keyword):
    """标准化商品数据"""
    if platform == "temu":
        return {
            "platform": "temu",
            "title": item.get("title", "") or item.get("goods_name", ""),
            "price": item.get("price_info", {}).get("price", "") or item.get("price", ""),
            "image": item.get("image", {}).get("url", "") or item.get("image", ""),
            "url": item.get("link_url", "") or item.get("url", ""),
            "sales_tip": item.get("sales_tip", "") or item.get("sales", ""),
            "comment": item.get("comment", "") or item.get("comment_count", ""),
            "keyword": keyword,
        }
    elif platform == "shein":
        return {
            "platform": "shein",
            "title": item.get("goods_name", "") or item.get("title", ""),
            "price": item.get("salePrice", {}).get("amountWithSymbol", "") or item.get("price", ""),
            "image": item.get("goods_img", "") or item.get("image", ""),
            "url": item.get("链接", "") or item.get("url", "") or item.get("goods_url", ""),
            "sales_tip": item.get("sales_tip", "") or "",
            "comment": item.get("comment", "") or "",
            "keyword": keyword,
        }
    elif platform == "etsy":
        return {
            "platform": "etsy",
            "title": item.get("title", ""),
            "price": item.get("price", ""),
            "image": item.get("image", ""),
            "url": item.get("listingUrl", "") or item.get("url", ""),
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


def collect_platform(platform, keywords):
    """采集单个平台"""
    all_items = []
    per_kw = PER_KEYWORD_LIMIT[platform]

    print(f"\n{'='*50}")
    print(f"开始采集 {platform.upper()}")
    print(f"关键词: {keywords}")
    print(f"每关键词目标: {per_kw} 条")
    print(f"{'='*50}")

    for keyword in keywords:
        items = run_actor(platform, keyword, per_kw)
        normalized = []
        for item in items:
            n = normalize_item(platform, item, keyword)
            if n.get("title"):
                normalized.append(n)
        print(f"  标准化后: {len(normalized)} 条（过滤前）")

        # 过滤POD相关
        filtered = [n for n in normalized if is_pod_product(n["title"])]
        print(f"  POD过滤后: {len(filtered)} 条")
        all_items.extend(filtered)

    # 保存原始数据
    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = RAW_DIR / f"{platform}_{today}.json"
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"\n{platform.upper()} 采集完成: {len(all_items)} 条，已保存到 {raw_file}")

    return all_items


def main():
    ensure_dirs()

    if not APIFY_TOKEN:
        print("错误: 未设置 APIFY_TOKEN 环境变量")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"{'='*60}")
    print(f"PrintVerse 采集任务 v2 - {today}")
    print(f"Token: {APIFY_TOKEN[:10]}...")
    print(f"{'='*60}")

    all_products = []

    # 采集各平台
    all_products.extend(collect_platform("temu", TEMU_KEYWORDS))
    all_products.extend(collect_platform("shein", SHEIN_KEYWORDS))
    all_products.extend(collect_platform("etsy", ETSY_KEYWORDS))

    # 去重（按标题）
    seen_titles = set()
    unique_products = []
    for p in all_products:
        title_key = p["title"].strip().lower()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_products.append(p)

    print(f"\n{'='*60}")
    print(f"采集汇总")
    print(f"{'='*60}")
    print(f"总采集（过滤后）: {len(all_products)} 条")
    print(f"去重后: {len(unique_products)} 条")
    for platform in ["temu", "shein", "etsy"]:
        count = len([p for p in unique_products if p["platform"] == platform])
        print(f"  {platform}: {count} 条")

    # 全平台0条时警告并返回错误码
    if len(unique_products) == 0:
        print("\n⚠️ 警告：所有平台均未采集到数据！")
        print("可能原因：网络问题、Apify额度耗尽、目标平台反爬")
        print("请检查上方日志中各平台的详细错误信息")
        sys.exit(2)

    # 下载图片
    print(f"\n{'='*60}")
    print(f"下载商品图片")
    print(f"{'='*60}")
    success_count = 0
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
                    success_count += 1
            else:
                product["local_image"] = f"data/images/{img_name}"
                success_count += 1

    print(f"图片下载成功: {success_count}/{len(unique_products)}")

    # 保存汇总数据
    products_file = DATA_DIR / "products.json"
    output = {
        "updated_at": datetime.now().isoformat(),
        "total": len(unique_products),
        "by_platform": {
            "temu": len([p for p in unique_products if p["platform"] == "temu"]),
            "shein": len([p for p in unique_products if p["platform"] == "shein"]),
            "etsy": len([p for p in unique_products if p["platform"] == "etsy"]),
        },
        "products": unique_products,
    }
    with open(products_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n汇总数据已保存: {products_file}")

    # GitHub Actions输出（使用新的Environment Files语法）
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"total={len(unique_products)}\n")
            f.write(f"temu={output['by_platform']['temu']}\n")
            f.write(f"shein={output['by_platform']['shein']}\n")
            f.write(f"etsy={output['by_platform']['etsy']}\n")
        print("已写入GitHub Actions输出")

    print(f"\n{'='*60}")
    print(f"采集完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
