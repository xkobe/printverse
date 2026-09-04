#!/usr/bin/env python3
"""
PrintVerse AI变体图案生成脚本
读取采集的商品数据，生成AI变体图案
- 有GPU API Key时：调用AI绘图API生成变体
- 无API Key时：用Pillow做基础变体处理（占位，后续替换为AI）
"""
import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps

DATA_DIR = Path(__file__).parent.parent / "data"
VARIANTS_DIR = DATA_DIR / "variants"
PRODUCTS_FILE = DATA_DIR / "products.json"

# AI绘图API配置（通过环境变量设置）
AI_API_KEY = os.environ.get("AI_IMAGE_API_KEY", "")
AI_API_ENDPOINT = os.environ.get("AI_IMAGE_API_ENDPOINT", "")
AI_API_PROVIDER = os.environ.get("AI_IMAGE_API_PROVIDER", "none")  # volcengine / replicate / none


def ensure_dirs():
    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_variant_with_api(image_path, prompt, output_path):
    """调用AI绘图API生成变体图案"""
    if not AI_API_KEY or not AI_API_ENDPOINT:
        return False

    try:
        # 读取原图并转base64（如果API需要）
        # 这里预留接口，具体根据API提供商实现
        print(f"    调用AI API生成变体: {AI_API_PROVIDER}")

        if AI_API_PROVIDER == "volcengine":
            # 火山引擎Seedream API调用（需要实现签名）
            # 参考: https://www.volcengine.com/docs/6791/1296750
            pass
        elif AI_API_PROVIDER == "replicate":
            # Replicate API调用
            pass

        return False  # 暂未实现具体API调用
    except Exception as e:
        print(f"    API调用失败: {e}")
        return False


def generate_basic_variant(image_path, output_path, variant_type=0):
    """用Pillow生成基础变体（占位方案）"""
    try:
        img = Image.open(image_path).convert("RGBA")

        if variant_type == 0:
            # 水平翻转
            img = ImageOps.mirror(img)
        elif variant_type == 1:
            # 增强对比度
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.3)
        elif variant_type == 2:
            # 调整亮度
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.1)
        elif variant_type == 3:
            # 增强色彩
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.2)

        # 保存为PNG
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"    基础变体生成失败: {e}")
        return False


def main():
    ensure_dirs()

    if not PRODUCTS_FILE.exists():
        print("错误: 未找到 products.json，请先运行采集脚本")
        sys.exit(1)

    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    products = data.get("products", [])
    print(f"=== PrintVerse 变体生成任务 ===")
    print(f"待处理商品: {len(products)} 个")
    print(f"AI API提供商: {AI_API_PROVIDER}")

    if AI_API_PROVIDER == "none" or not AI_API_KEY:
        print("提示: 未配置AI绘图API，将使用Pillow基础变体（占位）")
        print("      配置 AI_IMAGE_API_KEY 和 AI_IMAGE_API_ENDPOINT 后启用AI变体")

    variants = []

    for i, product in enumerate(products):
        title = product.get("title", "unknown")[:40]
        platform = product.get("platform", "unknown")
        local_image = product.get("local_image", "")

        print(f"\n[{i+1}/{len(products)}] {platform}: {title}...")

        if not local_image:
            print("    跳过: 无本地图片")
            continue

        image_path = DATA_DIR.parent / local_image
        if not image_path.exists():
            print(f"    跳过: 图片不存在 {image_path}")
            continue

        # 为每个商品生成2个变体
        product_variants = []
        for v in range(2):
            variant_name = f"{platform}_{i:03d}_v{v}.png"
            variant_path = VARIANTS_DIR / variant_name

            success = False
            if AI_API_KEY and AI_API_ENDPOINT:
                success = generate_variant_with_api(image_path, title, variant_path)

            if not success:
                success = generate_basic_variant(image_path, variant_path, v)

            if success:
                variant_data = {
                    "variant_id": f"{platform}_{i:03d}_v{v}",
                    "source_platform": platform,
                    "source_title": product.get("title", ""),
                    "source_image": local_image,
                    "variant_image": f"data/variants/{variant_name}",
                    "variant_type": "ai" if AI_API_KEY else "basic",
                    "created_at": datetime.now().isoformat(),
                    "status": "pending_review",  # 待审核
                }
                product_variants.append(variant_data)
                print(f"    变体{v+1}已生成: {variant_name}")

        variants.extend(product_variants)

    # 保存变体数据
    variants_file = DATA_DIR / "variants.json"
    output = {
        "updated_at": datetime.now().isoformat(),
        "total": len(variants),
        "ai_enabled": bool(AI_API_KEY and AI_API_ENDPOINT),
        "variants": variants,
    }
    with open(variants_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n=== 变体生成完成 ===")
    print(f"生成变体: {len(variants)} 个")
    print(f"数据已保存: {variants_file}")
    print(f"::set-output name=variants::{len(variants)}")


if __name__ == "__main__":
    main()
