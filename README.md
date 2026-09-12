# ClavisSinica 状态页

外部探针 + GitHub Pages。**探针跑在 GitHub 的机器上，不在被探测的服务器上**——这是这个页面存在的全部意义：我们的机器挂了，页面照常报告。

## 一、建仓库（你来做，五步）

1. GitHub 上新建**公开**仓库，建议名 `clavissinica-status`。
   不要勾 "Add a README"，空仓库最省事。

2. 把这个目录的内容原样推上去：

   ```
   clavissinica-status/
   ├── index.html
   ├── status.json                    ← 初始空状态，第一次探测后被覆盖
   ├── README.md
   ├── scripts/probe.py
   └── .github/workflows/probe.yml
   ```

   ```bash
   cd <解压出来的目录>
   git init -b main
   git add -A
   git commit -m "status page: external probe + pages"
   git remote add origin git@github.com:<你的用户名>/clavissinica-status.git
   git push -u origin main
   ```

3. 开 Pages：仓库 **Settings → Pages → Source 选 "Deploy from a branch"**，
   分支 `main`，目录 `/ (root)`，保存。
   一两分钟后地址是 `https://<你的用户名>.github.io/clavissinica-status/`

4. 给 Actions 写权限：**Settings → Actions → General → Workflow permissions**，
   选 **Read and write permissions**，保存。
   （workflow 里已经声明了 `permissions: contents: write`，但仓库级设置是只读时它不生效。**这一步漏了的话，探测会跑、commit 会失败，而页面永远停在空状态**。）

5. 手动跑一次确认：**Actions → probe → Run workflow**。
   跑完看仓库里 `status.json` 的 `generated_at` 有没有变。

之后每 5 分钟自动跑一次。

## 二、跑起来之后要确认的三件事

- `status.json` 的 `generated_at` 在变（说明 commit 权限对了）
- 页面上五个组件都是绿的，且 `Ledger` / `Decomposition engine` 不是灰的
  （灰色说明探针拿不到 `/api-health` 的 body，多半是被 CDN 或 WAF 挡了）
- 首次跑完 24 小时后，"Last 24 hours" 那条应当是密集的，中间没有大片灰
  ——大片灰说明 GitHub 的 cron 被延迟或跳过了，那是它的正常行为，不是我们的故障

## 三、探什么

五个组件，全部来自**公开端点**，不碰内网，页面上不出现任何 IP、端口或上游服务名。

| 组件 | 判据 |
|---|---|
| API | `GET /api-health` 返回 200 |
| Authentication | `GET /v1/chinese/services` **不带 Key** 返回 401 |
| Decomposition engine | `/api-health` 的 body 里 `checks.upstream === true` |
| Ledger | `/api-health` 的 body 里 `checks.database === true` |
| Docs site | `https://clavissinica.org/` 返回 200 |

**第三、四项必须读 body。** `/v1/health` 在上游挂掉时仍然返回 HTTP 200，只在 body 里写 `status: "degraded"`。只看状态码的监控会一路绿到底——那正是这个页面要解决的问题，不能自己再犯一次。

## 四、这个页面刻意不做的事

**不承诺 SLA。** 页面上只有实测数字和「measuring since」的起始时间。跑了两小时就显示「100% 可用」是一句误导，所以样本数一直显示在旁边。

**缺样本画成灰色，不画成绿色。** GitHub 的 cron 是尽力而为的，会延迟也会跳过。「没测」和「测了没事」是两件事，页面上必须能分开。

**探测失败不让 workflow 变红。** 失败本身就是要记录的数据。让 Actions 一片红只会让真正的 workflow 故障淹没在里面。

## 五、成本与保留

- Actions：每次约 10 秒，每天 288 次 ≈ 48 分钟/天。公开仓库的 Actions 免费。
- 提交：每天最多 288 次，`status.json` 恒定几十 KB（明细只留 24 小时，日聚合只留 90 天）。
- 想降频改 `.github/workflows/probe.yml` 里的 cron。**GitHub 的最小间隔就是 5 分钟**，写更小的值不会更快。

## 六、上线之后要改的两处对外文档

页面跑起来、地址确定之后，这两处要加链接，否则又是一次「做了但没人知道」：

- `guide.html` / `guide.zh.html` 的**已知限制**一节，「No uptime SLA」那条旁边
- `llms.txt`

顺带把 `verify_lang_parity.py` 的 `FACTS` 加一行（状态页地址），让两版一致这件事继续被机器盯着。
