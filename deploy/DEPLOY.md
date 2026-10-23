# 服务器部署步骤（腾讯云轻量应用服务器）

> 当前进度：域名 + 服务器已购，ICP 备案流程在走。
> 结论：**现在就能把后端在服务器上跑起来**（备案下来前用服务器 IP 验证）；
> 但**公网正式访问（HTTPS）+ 微信小程序白名单**必须等备案通过后做。

---

## 前置确认
- 服务器地域：**中国大陆**（否则无法备案 / 微信不认域名）
- 系统：Ubuntu 22.04（轻量应用服务器镜像）
- 域名：已实名认证，且**域名所有者 = 备案主体**（个人姓名一致）
- 本地：代码已就绪（`miniapp-backend` / `miniapp-frontend`）

---

## 步骤 1：登录服务器，装基础环境
```bash
ssh root@<你的服务器公网IP>
apt update && apt upgrade -y
apt install -y python3-venv python3-pip git nginx
pip3 install gunicorn
```

## 步骤 2：传代码 + 装依赖 + 建 .env
**方式 A（推荐，可复现）：git clone**
```bash
cd /opt
git clone <你的仓库地址> miniapp-backend
cd miniapp-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-prod.txt   # 含 gunicorn
```
**方式 B：本地 scp 整个目录**（`.env` / `.venv` 不会跟着传，正好）

**手动建 .env（最关键，服务器上没有）**
```bash
nano /opt/miniapp-backend/.env
```
内容（照本地 .env 填，关键是真实 DOUBAO_API_KEY + 模型名）：
```
LLM_PROVIDER=doubao
DOUBAO_API_KEY=ark-你的真实key
DOUBAO_MODEL=doubao-seed-2-1-pro-260915        # 方舟按量模型；Agent Plan 套餐改用 doubao-seed-2.1-lite
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3   # 方舟按量；Agent Plan 套餐改为 /api/plan/v3
CACHE_TTL=86400
```
> 切勿把 .env 提交 git（.gitignore 已忽略）。

## 步骤 3：gunicorn + systemd 守护（开机自启）
先用 gunicorn 手动验证能起，再做成服务：
```bash
cd /opt/miniapp-backend
source .venv/bin/activate
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 127.0.0.1:8000 app.main:app
# 能起就 Ctrl+C
```
做成开机自启服务（本仓库已附模板，按实际路径微调）：
```bash
cp deploy/systemd/miniapp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now miniapp
systemctl status miniapp     # 看到 active(running) 即成功
```
> `-w 2` 是 worker 数，2 核机器够用；路径按实际部署目录调整。

## 步骤 4：nginx 反代 + 域名解析 + HTTPS（⭐ 备案通过后做）
1. **域名解析**：DNSPod 加 A 记录 `@` 和 `www` 指向服务器公网 IP（若购机时勾了"一键配置域名解析"已自动完成，去控制台确认）。
2. **防火墙**：轻量控制台「防火墙」放通 **80 / 443**。
3. **免费 SSL**：腾讯云控制台 → SSL 证书 → 申请免费 DV 证书 → 下载 **Nginx 格式** → 上传到服务器 `/etc/nginx/ssl/`。
4. **配 nginx**（本仓库已附模板）：
```bash
cp deploy/nginx/miniapp.conf /etc/nginx/sites-available/miniapp
# 编辑把 your-domain.com 改成你的域名、证书路径改成实际上传路径
ln -s /etc/nginx/sites-available/miniapp /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 备案没通过前，如何先验证后端？
- 轻量防火墙**临时放通 8000 端口**，然后：
```bash
curl http://<公网IP>:8000/api/queryCarPrice -H "Content-Type: application/json" -d '{"keyword":"比亚迪 海豹"}'
```
- 返回 JSON 即全链路通（含豆包联网取价）。**验证完建议关掉 8000 端口**，对外只留 80/443。

## 步骤 5：H5 部署（同源，免跨域）

H5 走同源相对路径 `/api`（见前端 `src/config.ts`），由 nginx 反代到本机 8000，因此**无需单独配 CORS**；但要求 nginx 同时托管静态文件并反代 `/api`。

### 5.1 本地构建
```bash
cd miniapp-frontend
npm install            # 仅首次
npm run build:h5       # 产物输出到 dist/build/h5
```

### 5.2 上传到服务器
服务器先建目录：
```bash
mkdir -p /opt/miniapp-h5
```
本地（Git Bash / PowerShell 均可）上传：
```powershell
scp -r dist/build/h5/. root@<公网IP>:/opt/miniapp-h5/
```
服务器  
```bash
nginx -t && systemctl reload nginx  
```
> 更新 H5 时重复这条即可覆盖；若担心旧文件残留，先 `rm -rf /opt/miniapp-h5 && mkdir -p /opt/miniapp-h5` 再传。

### 5.3 nginx 配置（⭐ 备案前用精简版，无域名也能跑）
**⚠️ 关键：没有域名 / 备案没通过，千万别用 `miniapp.conf`**（它含 443 + 证书路径，`nginx -t` 会因证书不存在而失败，且 80 强制跳 HTTPS 会让 IP 也打不开）。

直接用仓库里准备好的纯 HTTP 模板 `deploy/nginx/miniapp-http-only.conf`（已含 `/api` 反代 + `/tools/` 静态路径，用 `server_name _` 匹配任意 IP）：

```bash
cp /opt/miniapp-backend/deploy/nginx/miniapp-http-only.conf /etc/nginx/sites-available/miniapp
ln -sfn /etc/nginx/sites-available/miniapp /etc/nginx/sites-enabled/miniapp
rm -f /etc/nginx/sites-enabled/default        # 避免和默认站点抢 80/default_server
nginx -t && systemctl reload nginx
```
> 此模板无需域名、无需证书，`http://<公网IP>` 直接可用。等域名 + 备案 + SSL 证书齐全后，再按 5.5 换回 `miniapp.conf`。

### 5.4 防火墙 + 验证
1. 轻量控制台「防火墙」放通 **80** 端口。
2. **后端必须 running**（H5 查价走 `/api` 反代到本机 8000）：`systemctl restart miniapp`。
3. 浏览器开 `http://<公网IP>` 能看到 H5 页面；试查一辆车能返回车型价 = 全链路通（http 浏览器提示"不安全"，备案前忽略）。

### 5.5 备案通过后切换
把仓库 `deploy/nginx/miniapp.conf`（完整版：443 + 证书 + 80→443 跳转）覆盖回去，申请腾讯云免费 DV 证书传到 `/etc/nginx/ssl/`，把 `server_name` 改成你的域名，再 `nginx -t && systemctl reload nginx`，之后用 `https://域名.com` 访问。

## 步骤 6：微信小程序（备案通过后）
1. 把 `src/config.ts` 的 `PROD_DOMAIN` 改成 `https://你的域名.com`；
2. `npm run build:mp-weixin`；
3. 微信开发者工具导入 `dist/build/mp-weixin` → 上传；
4. mp.weixin.qq.com → 开发设置 → **服务器域名 → request 合法域名** 加 `https://你的域名.com`；
5. 提交审核 → 发布。

---

## 步骤 7：mytools 静态工具部署（纯静态，可选）

「空间」里的 `mytools` 是一组**纯静态 H5 小工具**（CSS/JS 全内嵌，无构建、无后端、无 Node），例如 `createWXscheme`（微信小程序跳转链接生成器）。部署 = 上传文件 + nginx 一条静态路径，比 miniapp H5 更简单，且与主站**复用同一域名 / 证书 / 端口**。

### 7.1 上传工具文件
服务器建目录：
```bash
mkdir -p /opt/mytools
```
本地（工作区）上传整个 mytools 目录：
```powershell
scp -r D:/workspace/myself/mytools/. root@<公网IP>:/opt/mytools/
```
> 导航页 `mytools/index.html` 与工具 `mytools/createWXscheme/index.html` 一并上传；以后新增工具，只需在 `/opt/mytools/` 下建子目录放 `index.html`，并到导航页加一张卡片即可（模板注释已给出示例）。

### 7.2 nginx 配置（已并入模板）
仓库 `deploy/nginx/miniapp.conf`（HTTPS 完整版）与步骤 5.3 备案前精简版都已包含：
```nginx
location /tools/ {
    alias /opt/mytools/;
    index index.html;
}
```
- 访问 `https://域名.com/tools/` → 工具集合导航页
- 访问 `https://域名.com/tools/createWXscheme/` → 具体工具
> `alias` 与 `location` 末尾的 `/` 都必须带，否则路径拼接 404。改完执行 `nginx -t && systemctl reload nginx`。

### 7.3 ⚠️ 重要：复制功能依赖 HTTPS
`createWXscheme` 的「复制链接」用的是 `navigator.clipboard`，只在 **HTTPS 或 localhost** 安全上下文生效；否则走 `execCommand` 兜底，手机浏览器基本已失效。**因此该工具务必在备案后通过 `https://域名.com/tools/...` 访问**；备案前用 `http://IP/tools/...` 打开页面正常，但手机微信里点「复制」可能失灵。

### 7.4 本地预览（验证复制功能）
```bash
cd D:/workspace/myself/mytools
python -m http.server 8080
# 浏览器开 http://localhost:8080/  → localhost 属安全上下文，复制可用
```

### 7.5 文件已硬编码默认值
`createWXscheme/index.html` 内写死了默认 `appid` / `path` / `query`。部署到公网后任何人可见——确认这些是要公开的内容；如需改动，直接编辑该 HTML 后重新 scp 覆盖。

---

## 验证清单
- [ ] `systemctl status miniapp` 显示 active(running)
- [ ] `curl` 接口返回正确 JSON（含真实车型价）
- [ ] 备案通过后：浏览器 `https://域名.com` 能查价 / 测算（H5）
- [ ] 微信小程序 request 白名单已加，真机可查价 / 测算
- [ ] 改代码后：`systemctl restart miniapp`；改 nginx 后：`nginx -t && systemctl reload nginx`

## 常见卡点
- **改了代码不生效**：`systemctl restart miniapp`；
- **curl 不通**：检查轻量「控制台防火墙」+ 服务器内 `ufw status` 是否放通对应端口；
- **豆包调用超时**：服务器需能出公网访问 `ark.cn-beijing.volces.com`，默认能出；
- **HTTPS 证书报错**：确认证书是 Nginx 格式且路径正确，nginx -t 会给出具体行。
