# B 站 Cookie 获取指南

## 为什么需要 Cookie

B 站的 AI 字幕和评论 API 需要登录态才能正常返回数据。没有 Cookie 的情况下：
- 字幕 API 会返回空列表
- 评论 API 会被反爬机制拦截，返回 0 条评论

## 获取步骤

### Chrome 浏览器

1. 打开 [bilibili.com](https://www.bilibili.com) 并**登录**你的账号
2. 按 `F12` 打开开发者工具
3. 切换到 **Application**（应用程序）标签页
4. 在左侧找到 **Storage → Cookies → https://www.bilibili.com**
5. 你会看到一个 Cookie 列表，包含 `SESSDATA`、`bili_jct`、`buvid3` 等字段

### 复制 Cookie 字符串

**方法一：从 Network 面板复制（推荐）**

1. 在开发者工具中切换到 **Network**（网络）标签页
2. 刷新页面，随便点击一个请求
3. 在请求详情的 **Headers** 中找到 `Cookie` 字段
4. 右键复制整个 Cookie 值

**方法二：手动拼接关键字段**

从 Application → Cookies 中复制以下关键字段，用分号拼接：

```
SESSDATA=xxx; bili_jct=xxx; buvid3=xxx; DedeUserID=xxx
```

### 重要字段说明

| 字段 | 作用 | 必须 |
|------|------|------|
| `SESSDATA` | 登录凭证，最重要 | ✅ |
| `bili_jct` | CSRF Token | ✅ |
| `buvid3` | 设备标识 | ✅ |
| `DedeUserID` | 用户 ID | 推荐 |
| `bili_ticket` | 访问票据 | 推荐 |

## Cookie 有效期

- B 站 Cookie 通常有效期为 **30 天**
- 如果脚本运行时提示"Cookie 过期"或评论返回 0 条，需要重新获取
- 建议每次使用前检查 Cookie 是否仍然有效

## 安全提示

- Cookie 等同于你的登录凭证，**不要分享给他人**
- 仅在本地环境使用，不要上传到公开仓库
- 使用完毕后可以在浏览器中退出登录使 Cookie 失效
