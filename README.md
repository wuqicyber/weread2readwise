# 微信读书划线/笔记 → Readwise 同步工具

## 项目简介
本仓库提供一段 Python 脚本，可自动将 **微信读书** 中的划线与笔记同步至 **Readwise**。项目参考[weread_to_readwise](https://github.com/CharMingF/weread_to_readwise)

1. 自动获取书架、划线与笔记，并去重。
2. 通过 Readwise API 批量写入，并在终端输出响应信息（如未被跳过）。
3. 内置重试与 Cookie 刷新机制，网络不稳定时自动重试。


> 若脚本检测到某本书划线数与 Readwise 一致，则会 **跳过** 同步；否则执行写入并在终端打印 Readwise 的 HTTP 响应。  
> 这样既避免重复写入，也方便调试。

---

## 环境准备

```bash
# 创建虚拟环境（可选）
python -m venv venv
source venv/bin/activate  

# 安装依赖
pip install -r requirements.txt
```

`requirements.txt` 依赖：

```
requests
pytz
retrying
```

---

## 获取必要令牌

| 名称 | 说明 | 获取方式 |
| ---- | ---- | -------- |
| WEREAD_COOKIE | 微信读书网页版的完整 Cookie 字符串 | 打开 <https://weread.qq.com/>，浏览器中复制 `Cookie`
| READWISE_TOKEN | Readwise 个人 API Token | 账户设置 → **API Access** |

此外，若使用 CookieCloud，可额外设置：

- `CC_URL`   – CookieCloud 地址（默认 `https://cookiecloud.malinkang.com/`）
- `CC_ID`    – 节点 ID
- `CC_PASSWORD` – 访问密码

---

## 快速开始

### 方式 1：全部用环境变量

```bash
export WEREAD_COOKIE="wr_vid=xxx; wr_skey=yyy"
export READWISE_TOKEN="xxxxxxxxxxxxxxxxxxxx"

python main.py
```

### 方式 2：命令行参数

```bash
python main.py \
  -c "wr_vid=xxx; wr_skey=yyy" \
  -t "xxxxxxxxxxxxxxxxxxxx"
```

脚本将：

1. 拉取所有微信读书笔记本 → 遍历书籍；
2. 跳过已同步（划线数一致）书籍；
3. 对于新增/更新的书籍：
   - 收集划线、笔记与元数据；
   - 构造 Readwise 请求并提交；
   - 打印 Readwise API 响应（HTTP 状态码与 JSON）。


