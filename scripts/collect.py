#!/usr/bin/env python3
"""
PrintHunt 热销款采集脚本 v4 (MVP精简版)
- 只采集Temu平台
- 日榜：昨日销量TOP20 POD T恤
- 周榜：上周销量TOP20 POD T恤
- 采集字段：标题、价格、销量、评分、评论数、主图URL
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 配置
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
DATA_DIR = Path(__file__).parent.parent / "data"
IMAGES_DIR = DATA_DIR / "images"

# ============================================================
# Apify Actors（Temu专用，按可靠性排序）
# ============================================================
TEMU_ACTORS = [
    "apivault_labs~temu-product-scraper",      # 评分5.0，含销量/评分/评论
    "lentic_clockss~temu-scraper",              # 多区域支持
    "axlymxp~temu-product-scraper",             # 含sales count
]

# ============================================================
# 测试模式控制
# ============================================================
TEST_MODE = os.environ.get("TEST_MODE", "true").lower() == "true"

if TEST_MODE:
    # 测试模式：极致省，日榜5条+周榜5条，总计10条
    DAILY_LIMIT = 5
    WEEKLY_LIMIT = 5
    print(f"[测试模式] 日榜{DAILY_LIMIT}条 + 周榜{WEEKLY_LIMIT}条，总计{DAILY_LIMIT+WEEKLY_LIMIT}条")
else:
    # 正式模式：日榜20条+周榜20条，总计40条
    DAILY_LIMIT = 20
    WEEKLY_LIMIT = 20
    print(f"[正式模式] 日榜{DAILY_LIMIT}条 + 周榜{WEEKLY_LIMIT}条，总计{DAILY_LIMIT+WEEKLY_LIMIT}条")

# ============================================================
# POD精准关键词（Temu T恤）
# ============================================================
TEMU_KEYWORDS = [
    "men graphic print t shirt",
    "vintage t shirt men",
    "funny slogan tee",
    "retro animal print shirt",
    "oversized graphic tee",
]

# ============================================================
# POD精准过滤（只保留印花T恤）
# ============================================================
CLOTHING_WORDS = ["shirt", "tee", "t-shirt", "tshirt", "hoodie", "sweatshirt"]
DESIGN_WORDS = [
    "graphic", "print", "printed", "vintage", "retro", "funny",
    "slogan", "quote", "animal", "floral", "cartoon", "skull",
    "band", "music", "game", "gamer", "gaming", "halloween",
    "christmas", "boho", "western", "minimalist", "art",
]
EXCLUDE_KEYWORDS = [
    "dress", "skirt", "pants", "jeans", "shorts", "shoe", "boot",
    "hat", "cap", "sock", "underwear", "bra", "pajama", "robe",
    "jacket", "coat", "blazer", "suit", "vest", "tank", "camisole",
    "lace", "silk", "satin", "cashmere", "wool", "linen",
    "basic", "solid", "plain", "blank", "white tee", "black tee",
    "polo", "henley", "v-neck basic", "crew neck basic",
]

def is_pod_tshirt(title):
    """三层过滤：排除词→服装词→印花词"""
    if not title:
        return False
    title_lower = title.lower()
    # 第一层：排除词
    for word in EXCLUDE_KEYWORDS:
        if word in title_lower:
            return False
    # 第二层：必须包含服装词
    has_clothing = any(w in title_lower for w in CLOTHING_WORDS)
    if not has_clothing:
        return False
    # 第三层：必须包含印花词
    has_design = any(w in title_lower for w in DESIGN_WORDS)
    if not has_design:
        return False
    return True

def run_actor(actor_id, keyword, limit):
    """运行Apify Actor采集Temu商品"""
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN, "timeout": 180}
    payload = {
        "keyword": keyword,
        "limit": limit,
        "country": "US",
        "sort": "sales",  # 按销量排序
    }
    try:
        resp = requests.post(url, params=params, json=payload, timeout=200)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  Actor {actor_id} 返回 {resp.status_code}: {resp.text[:100]}")
            return []
    except Exception as e:
        print(f"  Actor {actor_id} 异常: {e}")
        return []

def normalize_product(item, period):
    """标准化商品数据"""
    title = item.get("title") or item.get("name") or ""
    price = item.get("price") or item.get("currentPrice") or item.get("salePrice") or 0
    sales = item.get("sales") or item.get("salesCount") or item.get("orderCount") or 0
    rating = item.get("rating") or item.get("stars") or item.get("reviewRating") or 0
    reviews = item.get("reviews") or item.get("reviewCount") or item.get("commentsCount") or 0
    image = item.get("image") or item.get("mainImage") or item.get("photo") or item.get("imageUrl") or ""
    url = item.get("url") or item.get("productUrl") or item.get("link") or ""

    if isinstance(price, (int, float)):
        price_str = f"${price:.2f}"
    elif isinstance(price, str):
        price_str = price if price.startswith("$") else f"${price}"
    else:
        price_str = "$0.00"

    return {
        "id": item.get("id") or item.get("productId") or "",
        "title": title,
        "price": price_str,
        "sales": sales,
        "rating": float(rating) if rating else 0,
        "reviews": int(reviews) if reviews else 0,
        "image": image,
        "url": url,
        "platform": "Temu",
        "period": period,
        "collectedAt": datetime.now().isoformat(),
    }

def collect_period(period, limit):
    """采集指定周期的热销款"""
    print(f"\n{'='*50}")
    print(f"开始采集 {period} 榜单（目标{limit}条）")
    print(f"{'='*50}")

    all_products = []
    seen_titles = set()

    for keyword in TEMU_KEYWORDS:
        if len(all_products) >= limit:
            break
        print(f"\n搜索关键词: {keyword}")

        for actor in TEMU_ACTORS:
            if len(all_products) >= limit:
                break
            remaining = limit - len(all_products)
            fetch_limit = min(remaining + 5, 10)  # 多取5条用于过滤
            print(f"  使用Actor: {actor} (取{fetch_limit}条)")

            items = run_actor(actor, keyword, fetch_limit)
            print(f"  返回 {len(items)} 条原始数据")

            for item in items:
                if len(all_products) >= limit:
                    break
                title = item.get("title") or item.get("name") or ""
                if not title or title in seen_titles:
                    continue
                if not is_pod_tshirt(title):
                    continue
                seen_titles.add(title)
                product = normalize_product(item, period)
                all_products.append(product)
                print(f"    ✓ [{len(all_products)}/{limit}] {title[:50]}...")

            if all_products:
                time.sleep(2)  # 避免频繁请求

    print(f"\n{period}榜单采集完成: {len(all_products)}条")
    return all_products

def main():
    if not APIFY_TOKEN:
        print("❌ 未设置APIFY_TOKEN环境变量")
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"PrintHunt 采集脚本 v4 (MVP精简版)")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Token: {APIFY_TOKEN[:10]}...{APIFY_TOKEN[-4:]}")

    # 采集日榜和周榜
    daily_products = collect_period("daily", DAILY_LIMIT)
    weekly_products = collect_period("weekly", WEEKLY_LIMIT)

    # 合并保存
    all_products = daily_products + weekly_products
    output_file = DATA_DIR / "products.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "version": "v4-mvp",
            "collectedAt": datetime.now().isoformat(),
            "dailyCount": len(daily_products),
            "weeklyCount": len(weekly_products),
            "totalCount": len(all_products),
            "products": all_products,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"采集完成！")
    print(f"  日榜: {len(daily_products)}条")
    print(f"  周榜: {len(weekly_products)}条")
    print(f"  总计: {len(all_products)}条")
    print(f"  保存到: {output_file}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
