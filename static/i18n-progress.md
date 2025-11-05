# 主頁 i18n 國際化進度報告

## 已完成的工作 ✅

### 1. 翻譯文件更新
已完全更新了以下翻譯文件，添加了所有缺失的翻譯鍵：

- `app/i18n/locales/en-US.json` - 英文翻譯（新增約60個翻譯鍵）
- `app/i18n/locales/zh-CN.json` - 中文翻譯（新增約60個翻譯鍵）

### 2. 新增的翻譯類別

#### 郵件操作相關（email.mail.*）
- copy_tooltip, external_view_tooltip, delete_tooltip
- expand_collapse_tooltip, inbox_label, refresh_tooltip
- mails_count, from_label
- no_mails_title, no_mails_message, loading_mails

#### 郵件狀態（email.status.*）
- not_found, error, expired

#### 郵件詳情（email.details.*）
- loading, loading_content, data_not_loaded
- please_refresh, not_in_cache, cache_warning
- no_subject, unknown_sender, content_empty
- text_view, cannot_extract

#### 驗證碼（email.codes.*）
- found_count, not_found, extracting
- extract_button, extract_tooltip
- click_to_copy, close_tooltip

#### API 相關（api.*）
- descriptions.* (6個API描述)
- terminal.* (終端相關8個翻譯)
- cannot_parse_response, copy_url_tooltip, close_tooltip
- copy_failed, copied

#### 錯誤消息（errors.*）
- email_not_found_title, email_not_found_message

#### 用戶消息（messages.*）
- email_copied, code_copied
- confirm_delete, email_deleted
- auto_refresh_enabled
- api_notifications_enabled/disabled

#### 通用標籤（common_labels.*）
- random_domain, expired

### 3. JavaScript 代碼更新（app.js）

已完成部分國際化（約15-20%）：
- ✅ API 描述函數（getApiDescription）
- ✅ API 通知按鈕 tooltips
- ✅ 複製成功消息
- ✅ 隨機域名下拉選項
- ✅ 郵箱複製成功消息
- ✅ 郵箱刪除確認和成功消息

## 還需完成的工作 ⏳

### app.js 中仍需國際化的部分（約80-85%）

以下是主要需要替換的硬編碼中文文本位置：

#### 1. 郵箱列表渲染（renderEmailList函數）
- 行 528-530: 空狀態提示
- 行 551-556: 郵件狀態標記（未找到、錯誤、已過期）
- 行 579, 815: "X 封郵件"
- 行 584, 590, 596, 601: 操作按鈕 tooltips
- 行 616: "收件箱"
- 行 619: "刷新" tooltip

#### 2. 郵件列表渲染（renderMailList函數）
- 行 642-644: 空郵件狀態
- 行 663: "已找到 X 個驗證碼"
- 行 684-685: "未找到驗證碼"
- 行 708: "提取驗證碼"
- 行 712-713: "從:"、時間標籤
- 行 723: "提取中..."

#### 3. 郵件加載（fetchMailsForEmail函數）
- 行 749: "加載郵件中..."
- 行 838: 郵箱未找到錯誤提示

#### 4. 郵件詳情模態框（showMailDetail函數）
- 行 993-997: 加載狀態文本
- 行 1023-1029: 緩存錯誤提示
- 行 1038-1043: 郵件詳情字段（無主題、未知發件人等）
- 行 1051: 空內容提示
- 行 966: "文本"視圖模式

#### 5. 驗證碼提取相關
- 行 1075: 無法提取提示
- 行 1087, 1119: 提取中/提取驗證碼按鈕文本
- 行 1138, 1199-1231: 驗證碼列表渲染
- 行 1275-1360: 內聯驗證碼顯示

#### 6. 驗證碼複製（copyCodeFromChip等函數）
- 行 1404, 1444, 1459, 1485: 驗證碼已複製消息

#### 7. 自動刷新（toggleAutoRefresh函數）
- 行 1506-1507: "自動刷新: 關閉"
- 行 1514-1516: "自動刷新: 開啟"、成功提示
- 行 1937-1951: 初始化自動刷新文本

#### 8. 終端日誌（clearTerminalLog函數）
- 行 1873: 清空確認提示
- 行 1881: "API 調用監控已啟動..."
- 行 1887: "API 日誌已清空"
- 行 1799-1843: 終端渲染模板（請求、響應、Headers等）

#### 9. API 通知開關（toggleApiNotifications函數）
- 行 1899-1907: 彈窗通知狀態消息
- 行 1913: 關閉提示
- 行 1973-1984: 初始化文本

#### 10. 其他響應消息
- 行 97: "[無法解析響應體]"
- 行 362, 366: "複製失敗"錯誤（還需找到遺漏的）

## 測試建議

### 1. 基本測試
```bash
cd /Users/tomleung/Downloads/mcp/email
python3 run.py
```

訪問 `http://localhost:1234` 測試：
- ✅ 語言切換器應該顯示在導航欄
- ✅ 切換為英文，檢查 API 描述是否已英文化
- ✅ 生成郵箱，複製郵箱地址，檢查"郵箱已複製"消息
- ✅ 刪除郵箱，檢查確認對話框是否已國際化
- ⚠️ 其他部分可能仍顯示中文（未完成）

### 2. 後續完整國際化建議

由於還有約80%的硬編碼文本需要替換，建議採用以下方法之一：

**方法 A: 批量替換腳本**
創建 Python 腳本，使用正則表達式批量替換剩餘的硬編碼文本。

**方法 B: 逐步完成**
分批次完成剩餘部分：
1. 第一批：郵箱列表和郵件列表渲染（最常見）
2. 第二批：郵件詳情和驗證碼提取
3. 第三批：自動刷新和終端日誌
4. 第四批：其他輔助功能

**方法 C: 重構**
將 HTML 模板字符串提取到單獨的模板函數中，使用類似 Vue/React 的組件化方式，更容易管理國際化。

## 已添加的翻譯鍵完整列表

查看以下文件獲取完整的翻譯鍵列表：
- `app/i18n/locales/en-US.json`
- `app/i18n/locales/zh-CN.json`

每個翻譯鍵都有對應的英文和中文翻譯，確保語言切換時的一致性。

## 下一步建議

1. **優先完成高頻使用部分**：郵箱列表、郵件列表、郵件詳情
2. **測試現有國際化**：確保已完成部分正常工作
3. **逐步替換剩餘部分**：按功能模塊分批完成
4. **添加語言切換器樣式**：確保語言切換器在導航欄正確顯示

## 技術提示

使用 `safeT()` 函數調用翻譯：
```javascript
// 簡單翻譯
const text = safeT('email.mail.inbox_label');

// 帶參數的翻譯
const count = safeT('email.mail.mails_count', { count: 5 });

// 在模板字符串中
const html = `<span>${safeT('email.mail.inbox_label')}</span>`;
```
