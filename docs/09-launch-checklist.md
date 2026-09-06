# 09 上线准备清单（简历罗盘小程序 · 阶段一 个人主体）

> 目标：把「简历罗盘」小程序 + 后端/管理后台从本地开发环境发布到公网可用的生产环境。
> 阶段一 = 个人主体、**人工收款 + Web 后台发放次数包**（不接微信支付）；阶段二（个体户+微信认证+自动支付）见文末。

---

## 0. 一句话现状

功能已全部冒烟通过（方向匹配/方向报告/按此优化/岗位匹配/求职导航/管理后台发放）。
代码里一切开关均已按"生产"设计好：`WX_SECRET` 留空=开发模式（dev_ 测试号+自动补给），填上=真实登录并**关闭开发补给**（自动判 `wx_secret` 有无），`DEBUG=false` 即可上线。

---

## 0.5 服务器 / 域名选购（还没有的话看这里）

**结论先行：个人主体、阶段一（人工收款）下，最低成本方案 = 国内云「轻量应用服务器」+ 一个域名，总计约 ¥100–300/年（新人价）。**

| 资源 | 推荐 | 价格参考 | 说明 |
|---|---|---|---|
| 域名 | `.cn` / `.com`（个人实名即可） | 首年 ¥30–70 | **必须完成 ICP 备案**，微信合法域名才认 |
| 服务器 | 腾讯云/阿里云「轻量应用服务器」2核2G（Ubuntu 22.04） | 新用户活动约 ¥60–150/年 | 部署 API + Web 控制台足够；国内节点才能备案域名 |
| HTTPS 证书 | Let's Encrypt / 云厂商免费证书 | ¥0 | certbot 一键签发 |
| 数据库 | 服务器自带 PostgreSQL（或先用 SQLite） | ¥0 | MVP 够用 |

**注意顺序**：国内服务器 → 域名备案（约 1–3 周，需服务器已购；期间可先在本地继续开发）→ 备案通过 → 绑 HTTPS → 微信后台配域名。备案期间不影响继续测功能。

**不想备案的选项**：香港/境外轻量服务器免备案，但微信小程序 `request合法域名` 仍要求**已 ICP 备案**的域名才能配置，所以对"上线小程序"来说备案绕不开（除非只给内部用）。备案不收费，只是流程。

**购买建议**：
- 学生/新用户身份优先吃云厂商新人价；腾讯云"轻量应用服务器-学生机"或"双十一/新春活动"常见 2C2G≈¥100/年以内。
- 域名与服务器尽量同一家（如都在腾讯云），备案在一个控制台里走最顺。
- 备案域名解析到服务器 IP，备案期间服务器 IP 不能换（换了要重新备案接入）。

## 1. 需要准备的账号 / 材料

| 项 | 用途 | 状态/说明 |
|---|---|---|
| 小程序账号 | 上架运营 | 已有 `wx3d09f84d9f829852`（个人主体） |
| AppSecret | 真实 wx.login 换 openid | mp.weixin.qq.com → 开发管理 → 开发设置 → 生成后填入 `.env` 的 `WX_SECRET` |
| **已备案 HTTPS 域名** | 小程序 request/upload 合法域名、后端外网入口 | 微信要求：**ICP 备案 + HTTPS**，域名不能带端口、不能用 IP。无则先买域名并完成备案（见 §4） |
| 一台云服务器 | 跑 API + Web 控制台 | 2C2G 起（见 §0.5），国内云节点用于域名备案 |
| DeepSeek API Key | AI 引擎 | 已有（.env `DEEPSEEK_API_KEY`） |
| 收款渠道 | 客户付次数包钱 | 个人收款码/微信小商店等（人工） |
| 数据库 | 生产数据 | 推荐 PostgreSQL（也可先 SQLite，见 §5） |

---

## 2. 生产环境变量表（服务器 `.env`）

只列上线必须项；其余见 `apps/api/.env.example`。

| 变量 | 生产值示例 | 说明 |
|---|---|---|
| `DEBUG` | `false` | 关闭开发模式 |
| `DATABASE_URL` | `postgresql+asyncpg://resume:密码@127.0.0.1:5432/resume_saas` | SQLite 仅限本地 |
| `DEEPSEEK_API_KEY` | 真实 key | 主引擎 |
| `WX_APPID` | `wx3d09f84d9f829852` | 已在默认值，无需改 |
| `WX_SECRET` | 小程序 AppSecret | **必填**；空=开发模式 |
| `JWT_SECRET` | `openssl rand -hex 32` 结果 | **必改**，勿用默认 |
| `JWT_EXPIRE_DAYS` | `7` | |
| `CORS_ORIGINS` | `["https://你的域名"]` | Web 控制台如与 API 同源可不依赖 |
| `PUBLIC_BASE_URL` | `https://你的域名` | |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | 仅 B 端批量/自动刷新需要；C 端可不装 |
| `UPLOAD_DIR` | `data/uploads` | 建议绝对路径 + 定期备份 |

> 检查点：生产 `WX_SECRET` 有值 ⇒ dev_ 测试号不会再生效、开发自动补给自动关闭。

---

## 3. 后端部署步骤（Ubuntu 示例）

```bash
# 1) 代码与依赖
sudo apt update && sudo apt install -y python3.12-venv nginx redis-server
git clone <你的仓库> /opt/resume-saas && cd /opt/resume-saas
cd apps/api
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # 若无 requirements.txt 用 pip install -e . 按项目实际
# 2) 配置
cp .env.example .env                     # 按 §2 填好（DEBUG=false、WX_SECRET、JWT_SECRET…）
# 3) 前端产物（Web 控制台，随 API 同源托管）
cd ../web && npm ci && node node_modules/vite/bin/vite.js build   # 生成 dist
# 4) 首次启动会自动 create_all 建表 + SQLite 式补列迁移（生产用 PostgreSQL 时同样自动建表）
cd ../api
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**systemd 常驻（/etc/systemd/system/resume-api.service）**
```ini
[Unit]
Description=ResumeMatch API
After=network.target postgresql.service

[Service]
WorkingDirectory=/opt/resume-saas/apps/api
EnvironmentFile=/opt/resume-saas/apps/api/.env
ExecStart=/opt/resume-saas/apps/api/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now resume-api
```

**nginx HTTPS（/etc/nginx/sites-available/resume）**
```nginx
server {
  listen 80;
  server_name api.your-domain.com;
  location / { return 301 https://$host$request_uri; }
}
server {
  listen 443 ssl http2;
  server_name api.your-domain.com;
  ssl_certificate     /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;

  client_max_body_size 30m;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host;
               proxy_set_header X-Forwarded-Proto $scheme; proxy_set_header X-Real-IP $remote_addr; }
}
```
证书：`sudo certbot --nginx -d api.your-domain.com`（需域名已解析到本机）。

**（可选）Celery worker**：仅当使用 B 端批量分析/简历库自动刷新时需要；对应 systemd 服务跑 `celery -A app.worker.celery_app worker -P solo`（参照本地 dev-up）。

---

## 4. 域名与小程序合法域名（关键顺序）

1. 买域名（如 `your-domain.com`），备案主体可为个人或企业，**须先完成 ICP 备案**（腾讯云/阿里云控制台，约 1–3 周）。
2. 服务器绑定域名 + 签发 HTTPS 证书（§3）。
3. 小程序后台：mp.weixin.qq.com → 开发管理 → 开发设置 → **服务器域名**：
   - `request合法域名`：`https://api.your-domain.com`
   - `uploadFile合法域名`：`https://api.your-domain.com`（上传简历走 wx.uploadFile，必须同域加白）
4. 修改小程序请求地址：`apps/mp-compass/utils/config.js`：
   ```js
   API_BASE: 'https://api.your-domain.com/api/v1'   // 上线用；开发仍可指回 127.0.0.1:8000
   ```
5. **真机复测**：微信开发者工具 → 右上"详情"取消"不校验合法域名"勾选 → 手机真机预览，全流程（上传简历→方向匹配→报告/优化→岗位匹配→求职导航→我的→购买弹窗）逐项过一遍，确认没有因域名/证书导致的问题。

---

## 5. 数据库：生产建议 PostgreSQL

- 建库：
  ```sql
  CREATE USER resume WITH PASSWORD '强密码';
  CREATE DATABASE resume_saas OWNER resume;
  ```
- `DATABASE_URL=postgresql+asyncpg://resume:强密码@127.0.0.1:5432/resume_saas`
- 代码中 `JSONType` 已在 PostgreSQL 下自动用 `JSONB`；启动时 `create_all` 自动建表（当前无 Alembic，MVP 够用；数据量大/多人协作后再引入 Alembic 迁移）。
- 备份：每日 `pg_dump`（或 SQLite `cp data/resume.db`）+ 异地保留，简历上传目录一并备份。
- 从本地 SQLite 迁移：写个小脚本读 SQLite 表→写 PostgreSQL，或直接在服务器全新开始（推荐 MVP 直接全新开始）。

---

## 6. 上线前自检清单（照单打勾）

- [ ] `.env`：`DEBUG=false`、`WX_SECRET` 有值、`JWT_SECRET` 已改、`DEEPSEEK_API_KEY` 有效
- [ ] 域名已备案、HTTPS 可访问、小程序后台 request/uploadFile 域名已加白
- [ ] `apps/mp-compass/utils/config.js` 指向 https 域名
- [ ] 开发者工具关闭"不校验合法域名"后**真机**全流程复测通过
- [ ] 用真实 `wx.login`（非 dev_ 号）注册几个新用户，验证：新用户 1 次免费 → 第 2 个功能弹付费 → 后台"小程序用户"搜到 → 发放 → 到账
- [ ] Web 控制台：登录（管理员）→「小程序用户」页搜索/发放/流水 正常
- [ ] 小程序后台填写**《小程序用户隐私保护指引》**（收集简历文本/联系方式，用于 AI 分析），类目与实际功能一致（如 求职/招聘/工具 类）
- [ ] 上传代码：开发者工具"上传"→ 后台设体验版 → 自测 → **提审**（审核备注写清楚用途；次数包文案避免"保证找到工作"类承诺）→ 发布
- [ ] 服务器监控：日志落盘/轮转、DeepSeek 用量与账单查看、磁盘备份计划
- [ ] 收款-发放 SOP 确认：客户在哪看到 openid/昵称 → 客服在后台哪个菜单发放（写进运营小册）

---

## 7. 阶段二（自动支付）预留说明

- 个人主体**无法**开通微信支付/虚拟支付：需先办**个体工商户**执照 → 用该主体注册小程序（主体不可迁移，旧个人号一般注销重开）→ 微信认证（300 元/年）→ 申请微信支付商户号 → 后台开通对应类目支付。
- 代码侧已预留：计费/扣次与"发放"解耦（管理后台 `POST /admin/mp/grant` 即发放原子操作）；届时新增"支付回调 → 调 grant 写流水"即可，无需改动扣次/免费逻辑。
- 到时把 `wx_secret` 之外的 `mp_pack_pricing`、支付回调验签、订单表（可复用 `MpQuotaLog` 前加支付单字段或建 `mp_order` 表）接上即可。

---

## 8. 求助 C 端用户 openid 的方法

客户付款后要发次数包，需要定位用户：
- **"我的"页已展示"账号ID(openid)"并可一键复制**（个人主体阶段一运营闭环：客户复制 openid 发给客服）；
- Web 后台按 openid 或昵称搜索定位后发放。
