#!/usr/bin/env python3
"""
PrintHunt 热销款采集脚本 v3
优化：更换高评分Actor、精准POD关键词、增加销量/评分/评论字段、严格额度控制
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# 配置
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
IMAGES_DIR = DATA_DIR / "images"

# ============================================================
# Apify Actors（按可靠性排序，主选+备选）
# ============================================================
ACTORS = {
    "temu": [
        "apivault_labs~temu-product-scraper",      # 评分5.0，含销量/评分/评论，$3/1K
        "lentic_clockss~temu-scraper",              # 9天前更新，多区域支持
        "axlymxp~temu-product-scraper",             # 含sales count
    ],
    "shein": [
        "native_emblem~shein-product-scraper",      # 100%成功率，48/s，22字段
        "lentic_clockss~shein-scraper",             # $2.2/1K，8月30日更新
        "clearpath~shein-product-scraper",          # 2天前更新，快速模式
    ],
    "etsy": [
        "yumitori~etsy-listings-scraper",           # 已验证可用
    ],
}

# ============================================================
# 测试模式控制（测试期间用小数据量节省额度）
# ============================================================
TEST_MODE = os.environ.get("TEST_MODE", "true").lower() == "true"

# ============================================================
# POD精准关键词（按平台特性优化）
# ============================================================
if TEST_MODE:
    # 测试模式：极致省，每平台1词×3条，总计9条
    TEMU_KEYWORDS = ["graphic tee men"]
    SHEIN_KEYWORDS = ["men graphic tee"]
    ETSY_KEYWORDS = ["tshirt png sublimation"]
    PER_KEYWORD_LIMIT = {"temu": 3, "shein": 3, "etsy": 3}
    print(f"[测试模式-极致省] Temu 1词×3, Shein 1词×3, Etsy 1词×3, 总计9条")
else:
    # 正式模式：Temu每天20条，Shein/Etsy每天5条
    TEMU_KEYWORDS = ["graphic tee", "vintage t shirt", "funny slogan shirt", "retro animal print"]
    SHEIN_KEYWORDS = ["men graphic tee", "oversized print tee", "vintage graphic shirt"]
    ETSY_KEYWORDS = ["tshirt design png", "sublimation design", "retro shirt png", "quote shirt aesthetic"]
    PER_KEYWORD_LIMIT = {"temu": 5, "shein": 5, "etsy": 5}

# ============================================================
# POD精准过滤（只保留印花T恤/卫衣相关）
# ============================================================
POD_KEYWORDS = [
    "shirt", "tee", "t-shirt", "tshirt", "hoodie", "sweatshirt",
    "graphic", "print", "printed", "sublimation", "png", "design",
    "vintage", "retro", "funny", "slogan", "quote", "animal",
    "floral", "boho", "minimalist", "western", "halloween", "christmas",
]
# 排除词（非服装类）
EXCLUDE_KEYWORDS = [
    "dress", "skirt", "pants", "jeans", "shorts", "shoe", "boot",
    "bag", "purse", "wallet", "hat", "cap", "sock", "underwear",
    "bra", "panty", "swimsuit", "bikini", "coat", "jacket", "blazer",
    "phone case", "mug", "cup", "pillow", "poster", "sticker",
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


def build_actor_input(platform, actor_id, keyword, max_items):
    """根据不同actor构建输入参数"""
    # 通用搜索参数
    if "temu" in actor_id:
        if "apivault" in actor_id:
            return {"search": keyword, "max_items": max_items}
        elif "lentic" in actor_id:
            return {"searchQueries": [keyword], "maxItems": max_items}
        else:
            return {"searchQueries": [keyword], "maxItems": max_items}
    elif "shein" in actor_id:
        if "native_emblem" in actor_id:
            return {"search": keyword, "maxItems": max_items, "storeCode": "us"}
        elif "lentic" in actor_id:
            return {"searchQueries": [keyword], "maxItems": max_items}
        elif "clearpath" in actor_id:
            return {"searchQuery": keyword, "maxItems": max_items}
        else:
            search_url = f"https://us.shein.com/pdsearch/{keyword.replace(' ', '%20')}/"
            return {"startUrl": search_url, "results_wanted": max_items}
    elif "etsy" in actor_id:
        return {"queries": [keyword], "maxItems": max_items}
    return {}


def run_actor(platform, keyword, max_items, max_retries=2):
    """启动Apify Actor并等待完成，支持重试和备选actor"""
    actor_list = ACTORS[platform]

    for actor_idx, actor_id in enumerate(actor_list):
        run_input = build_actor_input(platform, actor_id, keyword, max_items)

        for attempt in range(max_retries):
            try:
                print(f"  [Actor {actor_idx+1}/{len(actor_list)}, 尝试 {attempt+1}/{max_retries}] {actor_id}")
                print(f"    输入: {json.dumps(run_input, ensure_ascii=False)}")

                # 启动运行
                result = apify_request("POST", f"/acts/{actor_id}/runs", run_input)
                run_id = result["data"]["id"]
                print(f"    Run ID: {run_id}")

                # 等待完成（最多3分钟，测试期缩短）
                for i in range(36):
                    time.sleep(5)
                    status = apify_request("GET", f"/actor-runs/{run_id}")
                    state = status["data"]["status"]
                    if state in ["SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"]:
                        duration = status["data"].get("stats", {}).get("durationMillis", 0) / 1000
                        print(f"    状态: {state} (耗时 {duration:.1f}s)")
                        break
                    if i % 6 == 0:
                        print(f"    等待中... ({state})")
                else:
                    print(f"    超时，跳过")
                    continue

                if state != "SUCCEEDED":
                    print(f"    运行失败: {state}")
                    if attempt < max_retries - 1:
                        time.sleep(3)
                    continue

                # 获取数据集
                dataset_id = status["data"]["defaultDatasetId"]
                items = apify_request("GET", f"/datasets/{dataset_id}/items")
                print(f"    获取到 {len(items)} 条原始数据")

                # 手动截断（部分actor不遵守maxItems参数）
                if len(items) > max_items:
                    items = items[:max_items]
                    print(f"    截断到 {max_items} 条")

                if items:
                    return items, actor_id
                else:
                    print(f"    ⚠️ 数据集为空，尝试下一个actor")
                    break

            except Exception as e:
                print(f"    采集异常: {type(e).__name__}: {str(e)[:100]}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                continue

    print(f"  {platform} 采集失败（已尝试所有actor）")
    return [], ""


def is_pod_product(title):
    """精准判断是否为POD印花T恤/卫衣"""
    if not title:
        return False
    title_lower = title.lower()

    # 排除非服装类
    for excl in EXCLUDE_KEYWORDS:
        if excl in title_lower:
            return False

    # 必须包含服装类词
    clothing_words = ["shirt", "tee", "t-shirt", "tshirt", "hoodie", "sweatshirt", "top"]
    has_clothing = any(w in title_lower for w in clothing_words)

    # 且包含印花/设计相关词，或者是vintage/funny等风格
    design_words = ["graphic", "print", "printed", "sublimation", "png", "design",
                    "vintage", "retro", "funny", "slogan", "quote", "animal",
                    "floral", "boho", "minimalist", "western"]
    has_design = any(w in title_lower for w in design_words)

    return has_clothing and (has_design or True)  # 放宽：只要是服装就保留


def safe_get(d, *keys, default=""):
    """安全获取嵌套字典值"""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d if d else default


def normalize_item(platform, item, keyword, actor_id):
    """标准化商品数据 - 统一字段"""
    result = {
        "platform": platform,
        "actor": actor_id,
        "keyword": keyword,
        "title": "",
        "price": "",
        "original_price": "",
        "image": "",
        "url": "",
        "sales_tip": "",
        "sold_count": "",
        "rating": "",
        "review_count": "",
        "shop": "",
        "collected_at": datetime.now().isoformat(),
    }

    if platform == "temu":
        result.update({
            "title": safe_get(item, "title", "goods_name", "name"),
            "price": safe_get(item, "price", "price_info", "price", "salePrice", "amount"),
            "original_price": safe_get(item, "originalPrice", "original_price", "marketPrice"),
            "image": safe_get(item, "image", "image_url", "goods_img", "mainImage"),
            "url": safe_get(item, "url", "link_url", "productUrl", "detailUrl"),
            "sales_tip": safe_get(item, "sales_tip", "salesTip", "soldText"),
            "sold_count": safe_get(item, "sold_count", "soldCount", "sales", "monthlySales"),
            "rating": safe_get(item, "rating", "ratingScore", "star"),
            "review_count": safe_get(item, "review_count", "reviewCount", "comments", "comment_count"),
            "shop": safe_get(item, "shop", "shopName", "store_name"),
        })
    elif platform == "shein":
        result.update({
            "title": safe_get(item, "goods_name", "title", "name", "productName"),
            "price": safe_get(item, "salePrice", "amountWithSymbol", "price", "currentPrice"),
            "original_price": safe_get(item, "retailPrice", "originalPrice", "marketPrice"),
            "image": safe_get(item, "goods_img", "image", "mainImage", "image_url"),
            "url": safe_get(item, "url", "goods_url", "productUrl", "detailUrl", "链接"),
            "sales_tip": safe_get(item, "sales_tip", "soldText"),
            "sold_count": safe_get(item, "sold_count", "orderCount", "sales"),
            "rating": safe_get(item, "rating", "avgRating", "star"),
            "review_count": safe_get(item, "review_count", "commentCount", "reviews"),
            "shop": "Shein",
        })
    elif platform == "etsy":
        result.update({
            "title": safe_get(item, "title", "name"),
            "price": safe_get(item, "price", "salePrice"),
            "image": safe_get(item, "image", "image_url", "mainImage"),
            "url": safe_get(item, "listingUrl", "url", "productUrl"),
            "sales_tip": safe_get(item, "sales_tip", "soldText"),
            "sold_count": safe_get(item, "sold_count", "numSales", "sales"),
            "rating": safe_get(item, "rating", "avgRating", "star"),
            "review_count": safe_get(item, "review_count", "numReviews", "reviews"),
            "shop": safe_get(item, "shop", "shopName", "store_name"),
        })

    # 确保URL完整
    if result["url"] and not result["url"].startswith("http"):
        if platform == "temu":
            result["url"] = "https://www.temu.com" + result["url"]
        elif platform == "shein":
            result["url"] = "https://us.shein.com" + result["url"]
        elif platform == "etsy":
            result["url"] = "https://www.etsy.com" + result["url"]

    return result


def download_image(url, save_path):
    """下载商品图片"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, timeout=20, stream=True, headers=headers)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    图片下载失败: {str(e)[:60]}")
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
        items, actor_used = run_actor(platform, keyword, per_kw)
        if not items:
            continue

        normalized = []
        for item in items:
            n = normalize_item(platform, item, keyword, actor_used)
            if n.get("title"):
                normalized.append(n)
        print(f"  标准化后: {len(normalized)} 条")

        # POD过滤
        filtered = [n for n in normalized if is_pod_product(n["title"])]
        print(f"  POD过滤后: {len(filtered)} 条")

        # 打印前3条标题用于调试
        for i, p in enumerate(filtered[:3]):
            print(f"    [{i+1}] {p['title'][:60]}... | ${p['price']} | 销量:{p['sold_count'] or 'N/A'}")

        all_items.extend(filtered)

    # 保存原始数据
    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = RAW_DIR / f"{platform}_{today}.json"
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"\n{platform.upper()} 采集完成: {len(all_items)} 条")

    return all_items


def main():
    ensure_dirs()

    if not APIFY_TOKEN:
        print("错误: 未设置 APIFY_TOKEN 环境变量")
        sys.exit(1)

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"{'='*60}")
    print(f"PrintHunt 采集任务 v3 - {today}")
    print(f"Token: {APIFY_TOKEN[:10]}...")
    print(f"测试模式: {TEST_MODE}")
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
        title_key = p["title"].strip().lower()[:80]
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

    # 全平台0条时警告
    if len(unique_products) == 0:
        print("\n⚠️ 警告：所有平台均未采集到数据！")
        print("可能原因：网络问题、Apify额度耗尽、Actor参数不匹配")
        print("请检查上方日志中各平台的详细错误信息")
        sys.exit(2)

    # 下载图片（测试期只下载前10张节省时间）
    print(f"\n{'='*60}")
    print(f"下载商品图片")
    print(f"{'='*60}")
    max_downloads = min(10, len(unique_products)) if TEST_MODE else len(unique_products)
    success_count = 0
    for i, product in enumerate(unique_products[:max_downloads]):
        if product.get("image"):
            img_ext = ".jpg"
            if ".png" in product["image"].lower():
                img_ext = ".png"
            img_name = f"{product['platform']}_{i:03d}{img_ext}"
            img_path = IMAGES_DIR / img_name
            if not img_path.exists():
                print(f"  [{i+1}/{max_downloads}] 下载: {product['title'][:30]}...")
                if download_image(product["image"], img_path):
                    product["local_image"] = f"data/images/{img_name}"
                    success_count += 1
            else:
                product["local_image"] = f"data/images/{img_name}"
                success_count += 1

    print(f"图片下载成功: {success_count}/{max_downloads}")

    # 保存汇总数据
    products_file = DATA_DIR / "products.json"
    output = {
        "updated_at": datetime.now().isoformat(),
        "version": "v3",
        "test_mode": TEST_MODE,
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

    # GitHub Actions输出
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
