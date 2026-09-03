# PrintVerse - 跨境POD热销图案AI变体下载平台

## 项目简介
面向中国跨境POD卖家的热销印花图案下载平台。后台自动采集Temu/Shein/Etsy热销榜单，AI反向提示词生成合规变体图案，前端搜索、筛选、预览、点数付费下载。

## 技术栈
- 纯静态HTML/CSS/JS（单文件）
- Hash路由，无需后端
- Cloudflare Pages 托管
- Apify API 采集热销榜单
- 百度网盘企业版 原图存储

## 本地运行
直接用浏览器打开 `index.html` 即可。

## 部署到 Cloudflare Pages（GitHub自动部署）

### 第一步：创建GitHub仓库
1. 登录 https://github.com
2. 点击右上角 `+` → `New repository`
3. Repository name 填 `printverse`
4. 选 `Public`
5. 不要勾选 "Add a README file"（已有）
6. 点击 `Create repository`

### 第二步：推送代码到GitHub
在项目目录执行：
```bash
git init
git add .
git commit -m "Initial commit: PrintVerse POD platform"
git branch -M main
git remote add origin https://github.com/你的用户名/printverse.git
git push -u origin main
```

### 第三步：Cloudflare Pages 连接GitHub
1. 登录 https://dash.cloudflare.com
2. 左侧菜单 → `Workers & Pages` → `Create` → `Pages` → `Connect to Git`
3. 选择GitHub，授权访问你的 `printverse` 仓库
4. 构建设置：
   - Framework preset: `None`
   - Build command: 留空（静态站点无需构建）
   - Build output directory: `/`（根目录）
5. 点击 `Save and Deploy`
6. 等待1-2分钟，部署完成后会获得一个 `xxx.pages.dev` 域名

### 第四步：绑定自定义域名（可选）
1. 在Cloudflare Pages项目 → `Custom domains` → `Set up a custom domain`
2. 输入你的域名（如 `printverse.com`）
3. 按提示配置DNS，Cloudflare会自动签发SSL证书

## 后续更新
修改代码后执行：
```bash
git add .
git commit -m "更新说明"
git push
```
Cloudflare Pages会自动检测到push并重新部署，无需手动操作。

## 页面路由
- `#/` - 首页（四平台热销款瀑布流）
- `#/detail/{id}` - 图案详情页（5tab样机预览+热销数据+AI变体说明）
- `#/recharge` - 充值中心（微信/支付宝点数充值）
- `#/profile` - 个人中心（下载记录/充值记录/退出登录）
- `#/login` - 登录注册
- `#/help` - 帮助中心
- `#/license` - 商用授权说明
- `#/admin` - 管理后台（仪表盘/素材审核/素材库/热销款采集/榜单数据/自动化任务/用户管理/IP黑名单/Apify配置）
